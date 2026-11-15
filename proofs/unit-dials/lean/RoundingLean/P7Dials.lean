import Mathlib

/-!
# Unit dials: the unit criterion for every number of dials, two dials, the δ lines and the
factor forms for four and five dials.
-/

namespace Rounding.P7

open Finset BigOperators

/-- `m i` divides `(∏ m) / m j` for `j ≠ i` -/
private lemma dvd_quot {k : ℕ} (m : Fin k → ℤ) (hm : ∀ i, 2 ≤ m i) (i j : Fin k) (hij : i ≠ j) :
    m i ∣ (∏ l, m l) / m j := by
  have hj : m j ≠ 0 := by have := hm j; omega
  rw [← Finset.mul_prod_erase Finset.univ m (Finset.mem_univ j), Int.mul_ediv_cancel_left _ hj]
  exact Finset.dvd_prod_of_mem m (Finset.mem_erase.2 ⟨hij, Finset.mem_univ i⟩)

/-- the sum reduces mod `m i` to its `i`-th term -/
private lemma sum_mod_i {k : ℕ} (m e : Fin k → ℤ) (hm : ∀ i, 2 ≤ m i) (i : Fin k) :
    (∑ l, e l * ((∏ j, m j) / m l)) ≡ e i * ((∏ j, m j) / m i) [ZMOD m i] := by
  rw [← Finset.add_sum_erase Finset.univ _ (Finset.mem_univ i)]
  have h0 : (∑ l ∈ Finset.univ.erase i, e l * ((∏ j, m j) / m l)) ≡ 0 [ZMOD m i] := by
    apply Int.modEq_zero_iff_dvd.2
    apply Finset.dvd_sum
    intro l hl
    exact Dvd.dvd.mul_left (dvd_quot m hm i l (Finset.ne_of_mem_erase hl).symm) _
  simpa using (Int.ModEq.refl (e i * ((∏ j, m j) / m i))).add h0

/-- **Claim 1, every number of dials.** Pairwise coprime moduli `m i ≥ 2`, `M` their product, signs `e i = ±1`:
every reading-back constant is `e i` exactly when the one congruence `∑ e i (M / m i) ≡ 1 (mod M)` holds. -/
theorem unit_iff_sum {k : ℕ} (m e : Fin k → ℤ) (hm : ∀ i, 2 ≤ m i)
    (hcop : ∀ i j, i ≠ j → IsCoprime (m i) (m j)) (he : ∀ i, e i * e i = 1) :
    (∀ i, (∏ j, m j) / m i ≡ e i [ZMOD m i]) ↔
      (∑ i, e i * ((∏ j, m j) / m i)) ≡ 1 [ZMOD (∏ j, m j)] := by
  constructor
  · intro h
    apply Int.modEq_iff_dvd.2
    apply Fintype.prod_dvd_of_coprime (fun i j hij => hcop i j hij)
    intro i
    apply Int.modEq_iff_dvd.1
    have h1 : e i * ((∏ j, m j) / m i) ≡ e i * e i [ZMOD m i] := (h i).mul_left (e i)
    rw [he i] at h1
    exact (sum_mod_i m e hm i).trans h1
  · intro h i
    have hd : m i ∣ ∏ j, m j := Finset.dvd_prod_of_mem m (Finset.mem_univ i)
    have h1 : e i * ((∏ j, m j) / m i) ≡ 1 [ZMOD m i] :=
      (sum_mod_i m e hm i).symm.trans (h.of_dvd hd)
    have h2 := h1.mul_left (e i)
    rw [← mul_assoc, he i, one_mul, mul_one] at h2
    exact h2

/-- **Claim 2, two dials.** For `2 ≤ a < b`: `b ≡ ±1 (mod a)` and `a ≡ ±1 (mod b)` iff `b = a + 1`.
(No coprimality hypothesis is needed.) -/
theorem two_dials (a b : ℤ) (ha : 2 ≤ a) (hab : a < b) :
    ((b ≡ 1 [ZMOD a] ∨ b ≡ -1 [ZMOD a]) ∧ (a ≡ 1 [ZMOD b] ∨ a ≡ -1 [ZMOD b])) ↔ b = a + 1 := by
  constructor
  · rintro ⟨_, h | h⟩
    · -- b ∣ 1 - a with 0 < a - 1 < b: impossible
      obtain ⟨q, hq⟩ := Int.modEq_iff_dvd.1 h
      rcases lt_trichotomy q 0 with hq0 | hq0 | hq0
      · nlinarith
      · subst hq0; omega
      · nlinarith
    · -- b ∣ -1 - a with 0 < a + 1 ≤ b: forces b = a + 1
      obtain ⟨q, hq⟩ := Int.modEq_iff_dvd.1 h
      rcases lt_trichotomy q (-1) with hq0 | hq0 | hq0
      · nlinarith
      · subst hq0; omega
      · rcases lt_trichotomy q 0 with h2 | h2 | h2
        · omega
        · subst h2; omega
        · nlinarith
  · intro h
    subst h
    refine ⟨Or.inl (Int.modEq_iff_dvd.2 ⟨-1, by ring⟩), Or.inr (Int.modEq_iff_dvd.2 ⟨-1, by ring⟩)⟩

/-- **The δ lines** (δ = 2t + 1). First line: `(t²+t−1, 2t²+t−2, 2t²+3t−1)`, with `a(b+c) − bc = 1`;
it gives (5,8,13) at t = 2, then (11,19,26), (19,34,43), … -/
theorem delta_line1 (t : ℤ) :
    (t ^ 2 + t - 1) * ((2 * t ^ 2 + t - 2) + (2 * t ^ 2 + 3 * t - 1))
      - (2 * t ^ 2 + t - 2) * (2 * t ^ 2 + 3 * t - 1) = 1 := by
  ring

/-- Second line: `(t²+t+1, 2t²+t+2, 2t²+3t+3)`, with `a(b+c) − bc = −1`; (3,5,8) at t = 1, (7,12,17), (13,23,30), … -/
theorem delta_line2 (t : ℤ) :
    (t ^ 2 + t + 1) * ((2 * t ^ 2 + t + 2) + (2 * t ^ 2 + 3 * t + 3))
      - (2 * t ^ 2 + t + 2) * (2 * t ^ 2 + 3 * t + 3) = -1 := by
  ring

/-- **Claim 4, the factor form** for the sign pattern (+, +, −, −): with `A = w + x`, `p = w x`,
`(A y − p)(A z − p) − (p² + s A) = A (y z (w + x) − w x (y + z) − s)`. -/
theorem four_factor (w x y z s : ℤ) :
    ((w + x) * y - w * x) * ((w + x) * z - w * x) - ((w * x) ^ 2 + s * (w + x))
      = (w + x) * (y * z * (w + x) - w * x * (y + z) - s) := by
  ring

/-- **Five dials, the criterion** (fix three, solve for two):
`(P y + Q e_y)(P z + Q e_z) − (σ P + Q² e_y e_z) = P (P y z + Q e_y z + Q e_z y − σ)`. -/
theorem five_factor (P Q y z ey ez σ : ℤ) :
    (P * y + Q * ey) * (P * z + Q * ez) - (σ * P + Q ^ 2 * ey * ez)
      = P * (P * y * z + Q * ey * z + Q * ez * y - σ) := by
  ring

end Rounding.P7
