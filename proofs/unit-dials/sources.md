# Unit dials: sources

Each line is from a page opened on 14 November 2026. A source that could not be opened, or was not read, says so.

## The law in its oldest form

Σ ±1/m_i ≡ 1/M (mod 1): a signed sum of unit fractions equal to one unit fraction.

| statement | source opened | what it says | status |
| --- | --- | --- | --- |
| Unit fractions: the Rhind papyrus | MacTutor, https://mathshistory.st-andrews.ac.uk/HistTopics/Egyptian_papyri/ and https://mathshistory.st-andrews.ac.uk/Biographies/Ahmes/ | "The Rhind papyrus gives a table for doubling unit fractions 1/n for n odd, n between 5 and 101." "The Recto contains division of 2 by the odd numbers 3 to 101 in unit fractions." The material is from an earlier work of about 2000 BC. | found. These pages do not give the date of the copy (about 1550 BC); they give Ahmes c. 1680–1620 BC |
| Two dials are the vernier | Vernier, *La construction, l'usage, et les propriétez du quadrant nouveau de mathématique*, Brussels 1631, Bayerische Staatsbibliothek Math.a. 245 (https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb10081202/manifest), pp. 10–11 and the dedication. "Pierre Vernier (c. 1580–1637)", International Hydrographic Review, https://journals.lib.unb.ca/index.php/ihr/article/download/28565/1882521320/1882521568 | Vernier: an arc of "trente & vn demy degrés", "diuisé en trente parties esgales seulement", each part "vaudra en operation vne minute de degré"; "le quotient de la diuision de trente ung: par trente, est ung & ung trentiesme". He names "Clauius & Nouius" before him. IHR: the nonius of Nunes in *De Crepusculis* (1542) "is a different one, although the principle is practically the same". | found. Vernier's scale is 30 parts against 31 half-degrees. No page opened writes 1/n − 1/(n+1) = 1/(n(n+1)) |
| Sunzi's problem: 3, 5, 7 with 70, 21, 15 | 孫子算經 卷下, https://zh.wikisource.org/wiki/孫子算經 , and https://yawnoc.github.io/sun-tzu/iii/26 | "凡三三數之，賸一，則置七十；五五數之，賸一，則置二十一；七七數之，賸一，則置十五。一百六以上，以一百五減之，即得。" ("For every remainder one counting by threes put seventy; by fives, twenty-one; by sevens, fifteen; at 106 or above subtract 105.") | found |
| 70, 21, 15 ≡ −35, +21, +15 (mod 105), so −1/3 + 1/5 + 1/7 = 1/105 | searched for this observation | Nearest: a course handout (https://people.cs.umass.edu/~immerman/cs250/L7Handout.pdf) with "35·2 ≡ 1 (mod 3) 21·1 ≡ 1 (mod 5) 15·1 ≡ 1 (mod 7)", which does not note 2 ≡ −1 | not found. Libbrecht, Needham and Martzloff were not opened |
| Fibonacci, *Liber Abaci* (1202): the 3, 5, 7 problem | Boncompagni's Latin edition (1857), p. 304, https://archive.org/details/bub_gb_w86fLKi88pYC ; Sigler (2002), notes to chapter 12, note 29, pp. 627–628 | "Diuidat excogitatum numerum per 3, et per 5, et per 7 … ex unaquaque unitate, que ex diuisione ternarij superfuerit, retine 70; … quinarii … 21; … septenarij … 15. Et quotiens numerus … ultra 105, eicias inde 105." A rule with a worked example (53), no reason given for the numbers. Sigler: "70r1 + 21r2 + 15r3 … congruent to n modulo 105". | found (chapter 12) |
| Fibonacci on unit fractions | Boncompagni p. 77; Sigler, introduction p. 8; arXiv 2502.05607 | "Incipit pars sexta septimi capituli de disgregatione partium in singulis partibus"; Sigler: "Leonardo discusses at length the separation of fractions into sums of unit fractions" | found (chapter 7). The passages read do not connect it with chapter 12 |

## Residue number systems

| source | what it states | status |
| --- | --- | --- |
| B. J. Babb, "Computing Fibonacci Numbers using the Chinese Remainder Theorem", Oregon State University REU Proceedings, 1989, https://math.oregonstate.edu/sites/math.oregonstate.edu/files/2022-04/7_Babb89.pdf , p. 5 | "in the case of three consecutive Fibonacci number[s]: i₁ ≡ (−1)ⁿ mod u_n, i₂ ≡ (−1)ⁿ⁺¹ mod u_{n+1}, i₃ ≡ (−1)ⁿ⁺¹ mod u_{n+2} (5). This makes finding the inverses a constant time process." Then (6): u_X ≡ r₁u_{n+1}u_{n+2} − r₂u_nu_{n+2} − r₃u_nu_{n+1} mod M (n even) | found: every constant of three consecutive Fibonacci moduli is ±1 |
| A. Hiasat, A. Sweidan, "Residue number system to binary converter for the moduli set (2^(n−1), 2^n − 1, 2^n + 1)", J. Systems Architecture 49 (2003) 53–58 | metadata only (Crossref) and a search snippet | not read |
| Patronik, Piestrak, "Design of reverse converters for the general RNS 3-moduli set {2^k, 2^n−1, 2^n+1}", EURASIP J. Adv. Signal Process., 2023 | abstract: no ±1 statement | full text not reached |
| Jaberipur, Nadimi, Kazemi, Lee, arXiv 2411.12213 (2024), {2^(2q+1), 2^q + 2^(q−1) ± 1} | no ±1 statement | read |
| a classification of moduli sets with every inverse ±1; "unity multiplicative inverse"; "inverse-free" reverse converters; z(x+y) = xy ± 1; (b − a)(c − a) = a² ± 1 | searched | not found |

## What the sources leave

| statement | in print, in the sources opened |
| --- | --- |
| Every constant of three consecutive Fibonacci moduli is ±1 | Babb 1989 |
| Dials n and n + 1 (the vernier) | Vernier 1631, Nunes 1542; not as 1/n − 1/(n+1) = 1/(n(n+1)) |
| Sunzi's constants are −35, +21, +15 modulo 105 | not found |
| Unit triples are exactly z(x + y) = xy ± 1 | not found |
| (2^k − 1, 2^k + 1, 2^(2k−1)) with constants (+1, −1, −1) | not found; Hiasat and Sweidan 2003 not read |
| (2^(n−1), 2^n − 1, 2^n + 1) with inverses (−1, 1, 1) | the subject of Hiasat and Sweidan 2003, not read |
| One congruence for any number of dials; the four- and five-dial factor forms | not found |
