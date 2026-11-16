// PBS count and correctness of ServerKey::scalar_mul_parallelized, radix, 2_2 parameters.
//
// Copied by the workflow to tfhe/examples/naf_scalar_mul_count.rs and run with:
//   NAF_LABEL=unpatched NAF_SAMPLES=200 \
//   cargo run --release --example naf_scalar_mul_count --features=integer,pbs-stats
//
// Builds unchanged against the unpatched and the patched tree: it only uses the public API.
// Random scalars come from a fixed-seed splitmix64, so both trees see the same scalars.

use std::time::Instant;
use tfhe::integer::{gen_keys_radix, ClientKey, RadixCiphertext};
use tfhe::shortint::parameters::PARAM_MESSAGE_2_CARRY_2_KS_PBS;
use tfhe::{get_pbs_count, reset_pbs_count};

struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

struct Stats {
    count: usize,
    pbs_sum: u64,
    pbs_max: u64,
    seconds: f64,
    failures: usize,
}

fn mask(width: u32) -> u64 {
    if width == 64 {
        u64::MAX
    } else {
        (1u64 << width) - 1
    }
}

fn main() {
    let label = std::env::var("NAF_LABEL").unwrap_or_else(|_| "unlabelled".to_string());
    let samples: usize = std::env::var("NAF_SAMPLES")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(200);
    let seed: u64 = std::env::var("NAF_SEED")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(20_261_115);

    // One key pair serves every width: the radix width is the number of blocks per ciphertext
    let (radix_cks, sks) = gen_keys_radix(PARAM_MESSAGE_2_CARRY_2_KS_PBS, 32);
    let cks: &ClientKey = radix_cks.as_ref();

    println!(
        "# label={label} samples={samples} seed={seed} threads={} params=PARAM_MESSAGE_2_CARRY_2_KS_PBS",
        rayon::current_num_threads()
    );
    println!("# label width kind scalar pbs ms result");

    let mut rng = SplitMix64(seed);
    let mut summary = Vec::new();
    let mut total_failures = 0usize;

    for width in [16u32, 32, 64] {
        let num_blocks = (width / 2) as usize;
        let m = mask(width);

        let mut cases: Vec<(&str, u64)> = vec![
            ("edge_zero", 0),
            ("edge_one", 1),
            ("edge_two", 2),
            ("edge_three", 3),
            ("edge_all_ones", m),
            // power of two: odd exponent needs an in-block shift, even exponent is a block rotation
            ("edge_pow2_odd_exponent", 1u64 << (width - 3)),
            ("edge_pow2_even_exponent", 1u64 << (width - 2)),
            ("edge_0b1011", 0b1011),
            ("edge_alternating", 0xAAAA_AAAA_AAAA_AAAA & m),
            ("edge_top_run", m ^ (m >> 2)),
        ];
        let edge_count = cases.len();
        for _ in 0..samples {
            cases.push(("random", rng.next() & m));
        }

        let mut stats = Stats {
            count: 0,
            pbs_sum: 0,
            pbs_max: 0,
            seconds: 0.0,
            failures: 0,
        };

        for (index, (kind, scalar)) in cases.iter().copied().enumerate() {
            let clear = rng.next() & m;
            let ct: RadixCiphertext = cks.encrypt_radix(clear, num_blocks);

            reset_pbs_count();
            let start = Instant::now();
            let result = sks.scalar_mul_parallelized(&ct, scalar);
            let elapsed = start.elapsed().as_secs_f64();
            let pbs = get_pbs_count();

            let decrypted: u64 = cks.decrypt_radix(&result);
            let expected = clear.wrapping_mul(scalar) & m;
            let ok = decrypted == expected;
            if !ok {
                stats.failures += 1;
            }

            println!(
                "{label} {width} {kind} {scalar} {pbs} {:.1} {}",
                elapsed * 1000.0,
                if ok { "ok" } else { "FAIL" }
            );

            if index >= edge_count {
                stats.count += 1;
                stats.pbs_sum += pbs;
                stats.pbs_max = stats.pbs_max.max(pbs);
                stats.seconds += elapsed;
            }
        }
        total_failures += stats.failures;
        summary.push((width, stats));
    }

    println!();
    println!("# summary label={label} (random scalars only; edge cases are listed above)");
    println!("| label | width | samples | mean PBS | worst PBS | mean ms | total s | failures |");
    println!("|---|---|---|---|---|---|---|---|");
    for (width, s) in &summary {
        let n = s.count.max(1) as f64;
        println!(
            "| {label} | {width} | {} | {:.1} | {} | {:.1} | {:.1} | {} |",
            s.count,
            s.pbs_sum as f64 / n,
            s.pbs_max,
            s.seconds * 1000.0 / n,
            s.seconds,
            s.failures
        );
    }

    if total_failures != 0 {
        eprintln!("{total_failures} incorrect products");
        std::process::exit(1);
    }
}
