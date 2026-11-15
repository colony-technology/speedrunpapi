# Spark tree: the junction and the turn between successive forks

What crosses a streamer fork, and how the plane of one fork stands against the plane of the fork before it, measured on a public record of laboratory discharges in three dimensions; the same turn asked of two lightning flashes.

Record: Guo and Nijdam, Plasma Sources Sci. Technol. 33, 045006 (2024), [doi:10.1088/1361-6595/ad37bf](https://doi.org/10.1088/1361-6595/ad37bf). Data: [Zenodo 10534905](https://zenodo.org/records/10534905), CC BY 4.0. 24 runs in air at 133 to 200 mbar and in nitrogen with 1 to 5 percent oxygen. Per run two files are read: `DataExp.mat`, the authors' fitted tree (each fork stored as a parent and two daughters, circular arcs, with a thickness D and a speed V per leg), and `StreamerFinal_in3D.mat`, the raw detections under those fits (one dot per strobe period, 25 to 40 ns, 5 to 8 mm apart along a path; points in millimetres).

Lightning: located radio sources of LOFAR. Flash 20A-7, `fig1a.dat` of DataverseNL [doi:10.34894/MGLPXM](https://doi.org/10.34894/MGLPXM), CC0 1.0, 6,445 sources of negative leaders at 9.5 to 11 km. Flash 21C-7, `21C7-C12sp.dat` of [Zenodo 7394137](https://zenodo.org/records/7394137), CC BY 4.0, 99,259 sources.

The data is not in this repository. `replay.sh` fetches the 24 `DataExp.mat` and the 24 `StreamerFinal_in3D.mat` members of `Experiments.zip` (877,340,999 B) from Zenodo by HTTP range, 21 MB and 104 MB; `fig1a.dat` from DataverseNL (612,504 B); `21C7-C12sp.dat` out of `AllFigures.zip` on Zenodo by HTTP range (9,429,815 B). All 50 files are checked against `record/data.sha256` and read as data by `src/geometry-tools/mat5load.py`, a MAT v5 reader on the Python standard library, or as text.

```
streamer forks, Guo and Nijdam 2024, 24 runs

1  junction balance, each leg pulls with D^a     across the parent's line   a = 2.04 (1.88 to 2.21)    396 forks, turns at 3 to 5 mm
                                                 along the parent's line    a = 1.91 (1.70 to 2.30)
                                                 another fork's thicknesses: across never closes (298 of 300)
2  what the fork conserves                       D^2 with each leg's direction  0.979 along, 0.988 across
                                                 D^2 as a number, (D1^2 + D2^2) / D0^2  1.158; is 1 at exponent 2.71 (2.47 to 3.08)
                                                 speed against thickness between sisters, V ~ D^k  k = 0.69 (0.64 to 0.73)
                                                 2 + 0.69 = 2.69 against 2.71: agreement unexplained
                                                 at the junction (raw dots): both daughters at 1.06 of the parent's speed;
                                                 D^2 v summed over the daughters 1.39 of the parent's
3  the plane of a fork against the fork before   stored planes  77.2 degrees, quartiles 61.2 and 85.2   577 pairs   control 43.1 (39.4 to 46.7)
   it, about the leg between them, 0 to 90       raw dots       75.3 degrees, quartiles 56.0 and 83.7   752 pairs   control 42.3 (39.2 to 45.5)
                                                 third fork against the first  40.5   152 chains   control 44.4 (37.6 to 52.0)

lightning, LOFAR
4  the same rotation                             21C-7  38.3 degrees  169 pairs  control 44.8 (38.2 to 51.6)
                                                 20A-7  54.7 degrees   31 pairs  control 42.5 (28.2 to 56.3)
                                                 the quarter turn does not show
```

Medians throughout; ranges in parentheses are 2.5th to 97.5th percentiles of bootstraps or of random pairings. Every stored path of `DataExp.mat` is a circular arc in a plane (see `proofs/fork-angle/`); sections 1 and 2 and the first half of section 3 read those fits. The raw dots carry no fit.

## 1. The junction balance: each leg pulls as its cross-section

`src/triangle2.py`, `record/triangle2.txt`. 689 forks with both daughters at least 16 mm and a thickness on all three legs. Thickness per leg: median of the stored D over 3 to 8 mm from the fork. h_k is the turn of daughter k from the parent's line.

Method. If each leg pulls on the junction along its own line with weight T = D^a, rest means two equations:

```
across the parent's line:   T1 sin h1 = T2 sin h2
along the parent's line:    T0 = T1 cos h1 + T2 cos h2
```

One unknown, two equations. For a from 0.5 to 4 the script takes, over the forks, the median of D_thick^a sin h_thick / (D_thin^a sin h_thin) (across) and of (D1^a cos h1 + D2^a cos h2) / D0^a (along), and finds where each is 1, with a bootstrap of 1,000 resamples of the forks. The law holds if one a satisfies both.

| reading of the turns | forks | across: a (bootstrap) | along: a (bootstrap) | another fork's thicknesses (300 shuffles) |
| --- | --- | --- | --- | --- |
| lines at 3 to 5 mm | 396 | 2.04 (1.88 to 2.21) | 1.91 (1.70 to 2.30) | across does not close in 298 of 300; along at 1.58 (1.51 to 1.66) |
| stored arcs' first chords | 680 | 1.86 (1.76 to 2.01) | 1.69 (1.54 to 1.93) | across never; along at 1.36 (1.30 to 1.42) |
| the record's Gamma1, Gamma2 | 661 | 1.55 (1.40 to 1.66) | 1.26 (1.14 to 1.43) | across never; along at 0.92 (0.87 to 0.98) |

At a = 2 and 3 to 5 mm: across 0.988, along 0.979. Fork by fork, log(sin turn of the thinner / sin turn of the thicker) against log(D thicker / D thinner) has slope 2.09 through the origin, rank correlation +0.593; the thicker daughter turns less in 0.886 of forks. The parent's thickness reckoned from the two daughters, (D1^a cos h1 + D2^a cos h2)^(1/a) at a = 2.04, over the stored one: 0.985 (quartiles 0.860 and 1.155), rank correlation +0.355.

Control: the same equations with the thicknesses of another fork. The across equation then has no a at which its median is 1. The along equation closes at a lower a with every reading.

Where turns and thickness are read at the same place (3 to 5 and 3 to 8 mm out), both equations hold by medians with one exponent near 2. With turns read nearer the stored fork point (first chords) or from the authors' own Gamma, the two exponents fall and part.

## 2. What the fork conserves, and the speed law

`src/kirchhoff.py`, `record/kirchhoff.txt`: the same 689 forks, thickness D as in section 1, speed V the one stored number per leg. `src/det_current.py`, `record/det_current.txt`: speeds from the raw dots beside each fork.

**As a number.** The median of (D1^2 + D2^2) / D0^2 is 1.158. The exponent n at which the median of (D1^n + D2^n) / D0^n is 1: 2.71 (bootstrap 2.47 to 3.08).

**The speed law between sisters.** V ~ D^k between the two daughters of one fork: slope of log(V1 / V2) on log(D1 / D2) through the origin 0.69 (bootstrap 0.64 to 0.73); median of the ratio of logs where the thicknesses differ by 16 percent or more, 0.63 (548 forks); the thicker daughter is the faster in 0.849. Thicker daughter against parent: slope -0.07, medians D ratio 0.889, V ratio 1.043. Thinner against parent: slope 0.49, D ratio 0.580, V ratio 0.800. Across all 2,046 legs within a condition: least-squares slope 0.46, rank correlation +0.495.

**Two measured numbers.** 2 + 0.69 = 2.69 and 2.71 agree to 0.02; with k = 0.69 the median of (D1^(2+k) + D2^(2+k)) / D0^(2+k) is 1.006 (1.016 at k = 0.63, 1.047 at k = 0.46). The agreement is unexplained. The current-like sum (D1^2 V1 + D2^2 V2) / (D0^2 V0) of the stored speeds is 1.117 (bootstrap 1.076 to 1.171), not 1. The last block of `record/kirchhoff.txt` prints these comparisons and nothing more.

**The speeds at the junction.** One dot per strobe period, so within a run the distance between two successive dots of a leg is its speed in mm per period. Parent's speed: the step from the dot before the fork dot to the fork dot. A daughter's first step: from the fork dot to its next dot. Its second step: between its next two dots. Thickness from the stored fork whose daughters' first points lie within 6 mm of the raw fork dot. 1,631 forks (daughters of 10 mm or more; a wider set than the 689, with (D1^2 + D2^2) / D0^2 = 1.304).

| | thicker daughter's speed over the parent's | thinner's | speed against thickness between sisters, k | (D1^2 v1 + D2^2 v2) / (D0^2 v0), bootstrap |
| --- | --- | --- | --- | --- |
| first step after the fork dot | 1.056 | 1.066 | -0.14 | 1.391 (1.360 to 1.429) |
| second step | 1.113 | 0.919 | 0.51 | 1.352 (1.316 to 1.409) |

The parent's last step is 6.51 mm per strobe period. The thicker daughter is the faster in 0.536 of forks at the first step and 0.826 at the second.

At the fork both daughters leave at the parent's speed; the speed law between sisters (k about 0.5 to 0.7) forms one strobe period later. Thickness squared times speed is not conserved through the fork as a number: the daughters carry 1.35 to 1.39 of the parent's. So the speed law does not hold at the junction, and the agreement of 2.69 with 2.71 is not read as conservation of current there.

What stands: with the daughters leaving at the parent's speed, the two balance equations of section 1 say that thickness squared, taken with each leg's direction, is conserved through the fork as a vector: along the parent's line 0.979, across it 0.988, exponent 2.0 from each equation; as a plain number it grows (1.158 on the 689 forks).

Control: none drawn. The intervals are bootstraps of the forks, 1,000 resamples.

## 3. Successive forks stand in quarter turns

### Stored planes

`src/planes.py`, `src/planes_check.py`, `src/planes_azimuth.py`; `record/planes.txt`, `planes_check.txt`, `planes_azimuth.txt`. The record stores each fork as its own triple of paths, in the authors' fitted branching plane for that fork; a leg between two forks is stored twice, once as a daughter of the first and once as the parent of the second. Discharges by number of stored forks, 24 runs: none 1,484, one 736, two 264, three 101, four 39, five 13, six 6.

Method. A second fork hangs on a first when its parent path starts within 4 mm of the start of one of the first fork's daughters: 577 pairs. Connecting leg 18.6 mm (quartiles 14.3 and 25.3). At the second fork the first fork's other daughter, the sibling, is 8.1 mm away. The plane of a fork is spanned by its two daughters' first chords. The rotation is the angle between the two planes about the connecting leg: both normals projected on the plane across the leg, the angle between them folded to 0 to 90 degrees.

| | median | quartiles | above 60 | below 30 | counts in bins of 15 degrees from 0 |
| --- | --- | --- | --- | --- | --- |
| the 577 pairs | 77.2 | 61.2, 85.2 | 0.759 | 0.113 | 30, 35, 26, 48, 118, 320 |
| each second fork with another tree's first fork (2,000 pairings) | 43.1 (39.4 to 46.7) | | 0.317 (0.279 to 0.354) | 0.354 (0.314 to 0.392) | |

None of the 2,000 pairings is as far from its own middle as the measured median. 320 of 577 pairs stand within 15 degrees of a right angle. Planes turned at random about a common line give 45.

Checks.
- The planes are the authors' fitted ones: the rotation is the same, 77.2 (61.2, 85.2), with the planes taken from the daughters' first chords (577), from lines fitted between 2 and 6 mm (574), or from end-to-end lines (577).
- The cameras' axes. In the record x is across the cameras' view, y is depth. The azimuth of the spread of all 1,824 stored forks is even over six bins of 30 degrees: 275, 310, 304, 293, 341, 301. Split by the azimuth of the first fork, the rotation's median is 74.2 to 79.2 in every bin, and the second fork's azimuth sits a quarter turn on from the first's (`record/planes_azimuth.txt`). Both forks at least 30 degrees from the depth axis: 227 pairs, 74.8. Both at least 45 degrees from it: 65 pairs, 37.6; that cut holds both spreads within 45 degrees of the x axis and so keeps pairs whose spreads are nearly parallel.
- Connecting leg of 12 mm or more, 477 pairs: 77.8 (quartiles 63.2, 85.5). The 20 pairs with a leg under 8 mm read 33.4; on the raw dots below the shortest legs read 75.1, so that number belongs to the two stored fits of a two-dot leg.
- Lean of the second fork's two daughters, across the leg, against the direction to the sibling: both away 0.120, both toward 0.224, one each 0.657; mean lean +0.021. The daughter nearer the sibling is the thicker one in 0.557 of 576.

### Raw dots

`src/det_planes.py`, `record/det_planes.txt`. All 24 `StreamerFinal_in3D.mat`; no fitted arc, no fitted plane. Each discharge's `FINAL.segment` list gives per segment its dots in order: column 1 the dot's id, columns 6 to 8 its x, y, z in mm. A fork is a dot that ends one segment and starts two. Its plane is spanned by the chords from the fork dot to each daughter's next dot, one strobe period on. A second fork hangs on a first when one of the first fork's daughter segments ends at the second fork's dot. Rotation as above, about the straight line joining the two fork dots.

2,719 discharges with segments, 1,991 forks, 752 pairs; connecting leg 19.2 mm, 3 strobe periods.

| | median | quartiles | above 60 | below 30 | counts in bins of 15 degrees from 0 |
| --- | --- | --- | --- | --- | --- |
| the 752 pairs | 75.3 | 56.0, 83.7 | 0.717 | 0.129 | 51, 46, 37, 79, 153, 386 |
| second forks with other trees' first forks (2,000 pairings) | 42.3 (39.2 to 45.5) | | 0.309 (0.277 to 0.342) | | |

None of the 2,000 pairings is as far. By the leg's length in strobe periods:

| connecting leg, strobe periods | 1 | 2 | 3 or 4 | 5 and more |
| --- | --- | --- | --- | --- |
| pairs | 141 | 190 | 281 | 140 |
| rotation, median | 75.1 | 76.2 | 75.5 | 73.4 |

The turn does not fade with the distance from the sibling. The opening by those first chords: 59.7 (quartiles 48.5, 70.9), a lower bound of the opening, since the split lies somewhere past the fork dot.

**Three forks in a row** (`src/det_planes2.py`, `record/det_planes2.txt`, 152 chains A, B, C, with B on a daughter of A and C on a daughter of B). The third fork's plane against the first: 40.5 (quartiles 13.7, 65.9); counts in bins of 15 degrees from 0: 41, 23, 17, 25, 18, 28, of which an even spread gives 25 each. Control, third forks with other trees' first forks: 44.4 (37.6 to 52.0), 0.286 of pairings as far. The quarter turns do not compose into a plain return: the rule is between a fork and the one before it. No hand: the shed branch turns one way in 0.441 of 152.

## 4. Lightning's radio maps: the quarter turn does not show

`src/cloud_planes.py` with `src/cloud_forks.py`; `record/cloud_21c7.txt`, `record/cloud_20a7.txt`. Sources in order of time, each tied to the nearest earlier one within 50 m; a fork is a node with two onward trails of at least 150 m and 150 m of trail behind it; directions are lines through a trail's sources between 15 and 60 m from the fork. A second fork hangs on a first when it lies on the main onward trail of one of the first fork's daughters. Rotation as above, about the line joining the two forks.

| flash | forks | pairs | trail between them | rotation, median (quartiles) | second forks with other pairs' first forks (2,000 pairings) | pairings as far |
| --- | --- | --- | --- | --- | --- | --- |
| 21C-7, whole flash | 245 | 169 | 88 m | 38.3 (18.9, 66.0) | 44.8 (38.2 to 51.6) | 0.058 |
| 20A-7, high negative leaders | 40 | 31 | 62 m | 54.7 (36.3, 70.0) | 42.5 (28.2 to 56.3) | 0.090 |

The quarter turn does not show in these two flashes with this reader. Level planes, held by the cloud's charge layers, do not show either: the vertical part of the planes' normals has median 0.570 and 0.572 (0.5 for planes turned at random), with 0.216 and 0.250 of them above 0.8.

Control: random pairing only. No control drawn for how well this reader finds a plane at this scale.

## Measurement and inference

**Measured.**
- Where turns and thickness are read at the same place, both balance equations hold by medians with one exponent, 2.04 across and 1.91 along. With the thicknesses of another fork the across equation does not close.
- Thickness squared with each leg's direction is conserved through the fork, 0.979 along and 0.988 across; as a number it grows, 1.158.
- The exponent at which thickness is conserved as a number, 2.71, and the speed law between sisters, 0.69. Their sum 2.69 agrees with 2.71; the agreement is unexplained.
- At the junction both daughters leave at the parent's speed; the speed law forms one strobe period later; thickness squared times speed grows through the fork by 1.35 to 1.39.
- The plane of a fork is turned a median of 77 degrees (stored planes) and 75 degrees (raw dots) against the plane of the fork before it on the same branch, where forks of different trees give 43 and 42. The third fork against the first gives 40.5 against 44.4. The second fork's daughters lean neither toward the sibling nor away.
- In two LOFAR flashes, with this reader, the rotation is 38.3 and 54.7 against 44.8 and 42.5.

**Inference, not measured.**
- The sibling's push. The sibling's charge pushes on the dividing head from one side; a division along that line would set one daughter against the sibling, so the head divides across it. The measurement says only that the second fork parts across the direction to its sibling.
- Faraday's tension. A tube of field lines pulls along itself with eps0 E^2 / 2 per unit area, so at equal field strength the pull of a tube is its cross-section times the field's energy density, which is its energy per length. A junction of three such tubes rests where the three pulls cancel, which is where the sum of energy per length times length is least. Whether a streamer's three legs are tubes at equal field strength is not shown here.
- If a head's charge goes as its cross-section at a fixed head field, the conserved vector of section 2 is charge times velocity, the rate of change of the discharge's dipole moment, which then passes through a split without a jump. Not measured.
- The triangle arithmetic, true whatever the physics: an even fork opens at 2 arccos(1 / (2 f)), f being each daughter's weight over the parent's. 72 degrees is f = 1 / phi (sides 1, 1, phi); 90 is T0^2 = T1^2 + T2^2; 120 is three equal weights. Whether heads divide at any of these weights is not measured.
- Analogies of form: the same alternation of planes appears in decussate leaves, the airways of a lung, an H-tree for a clock, the alternating axis of a k-d tree.

## What is known already

A search of the literature (15 November 2026; arXiv full texts, other items by abstract or as quoted where stated) found the following. It is a search, not a proof of absence.

On successive branching planes:
- For streamers, leaders, lightning, sprites and electrical trees, the search found no statement on the relative orientation of successive branching planes. Dijcks, van der Leegte and Nijdam (Plasma Sources Sci. Technol. 32, 045004, 2023) define a branch plane per event, "it is assumed that the three segments participating in the branching event lie on a 2D plane", and do not compare consecutive planes. Wang and co-authors (arXiv 2208.07279) and the review of Nijdam, Teunissen and Ebert (Plasma Sources Sci. Technol. 29, 103001, 2020) have no such statement.
- The tree model of Luque and Ebert (New J. Phys. 16, 013039, 2014) draws the direction of a split at random in the plane perpendicular to the parent: "each one is displaced from the straight path by a random vector +-dr in the plane perpendicular to the original streamer path". That is the random pairing of the controls above.
- For lungs, Sauret, Halson, Brown, Fleming and Bailey (J. Anat. 200, 123, 2002): "The rotation angle between two consecutive bifurcation planes is assumed to be 90°" in airway models, citing Martonen 1995 and Kitaoka 1999; measured by CT, mean 79 degrees (SD 41, n 229).

On the junction balance:
- Guo and Nijdam's abstract: "A linear relation between the streamer diameter ratio and the direction difference of two daughter branches is found, which intersects the vertical axis almost at unity." That is the subject of the across equation; their full text was not read.
- Wang and co-authors (arXiv 2208.07279, Appendix E): a relation R_A = k (R_B + R_C) with k about 1.3, "also consistent with the relation R_A^2 = R_B^2 + R_C^2 observed before", citing Nijdam and co-authors (Appl. Phys. Lett. 92, 101502, 2008) and Chen and co-authors (IEEE Trans. Dielectr. Electr. Insul. 25, 1128, 2018). The review of 2020 reports for Chen and co-authors a ratio r_parent^2 / (r_branch1^2 + r_branch2^2) of about 0.7.
- For arteries, Murray (J. Gen. Physiol. 9, 835, 1926), as given by Hagmeijer and Venner (arXiv 1812.09706): the branching angles of the laminar case, e0.e1 = -(R0^4 + R1^4 - R2^4) / (2 R0^2 R1^2) and its pair. These are the closure R0^2 e0 + R1^2 e1 + R2^2 e2 = 0, a triangle of forces with weights as cross-sections: the balance of section 1 with exponent 2. Murray's law of radii, R0^3 = R1^3 + R2^3, is a different statement.
- For streamers, leaders, lightning and electrical trees, the search found no force-balance, Maxwell-stress, Steiner or Murray description of the fork.

## Not done

- The balance at the split itself: the split lies inside one strobe period and is not observed in this record.
- The balance of section 1 on the raw dots of all 24 runs.
- A control drawn for plane orientation for the lightning reader; whether stepped negative leaders, which re-form at every step, keep any memory of the last fork.
- A selection effect of the stereo reconstruction against forks in the plane of the first fork cannot be excluded from the stored paths alone.
- Why 2 + 0.69 agrees with 2.71.
- Murray's original paper and Guo and Nijdam's full text were not read.
- In 19 of the 2,719 discharges of `StreamerFinal_in3D.mat` the segments have 9 columns instead of 11; `det_planes.py` reads columns 1 and 6 to 8 of them as of the others; they give 40 of the 1,991 forks and 20 of the 752 pairs. That columns 6 to 8 are x, y, z there is not checked.

## Replay

```sh
PYTHON=python3 bash replay.sh /path/to/new/data/dir     # Python 3 with NumPy and SciPy, curl, network to zenodo.org and dataverse.nl; exit 0 when every check holds
```

| step | what | expected |
| --- | --- | --- |
| 1 | `src/zipget.py`: the 24 `DataExp.mat` and 24 `StreamerFinal_in3D.mat` members of `Experiments.zip`; `fig1a.dat` from DataverseNL; `21C7-C12sp.dat` out of `AllFigures.zip` | 24 and 24 files, all 50 equal to `record/data.sha256` |
| 2 | `src/triangle2.py` on the directory | equal to `record/triangle2.txt`, line for line |
| 3 | `src/kirchhoff.py`, `src/det_current.py` on the directory | equal to `record/kirchhoff.txt`, `record/det_current.txt` |
| 4 | `src/planes.py`, `src/planes_check.py`, `src/planes_azimuth.py`, `src/det_planes.py`, `src/det_planes2.py` on the directory | equal to `record/`, line for line |
| 5 | `src/cloud_planes.py` on `21C7-C12sp.dat` and on `fig1a.dat` | equal to `record/cloud_21c7.txt`, `record/cloud_20a7.txt` |

Every random draw is seeded. Output goes to `build/`. Nothing in the data directory is run.

Recorded run: 15 November 2026, Apple M1, macOS 27.2, Python 3.11.18, NumPy 2.4.6, SciPy 1.17.1. A fresh clone of this branch into a new temporary directory, with an empty data directory, so that all 50 files were fetched fresh:

```sh
T=$(mktemp -d)
git clone REPOSITORY "$T/speedrunpapi"
cd "$T/speedrunpapi/proofs/spark-tree" && shasum -a 256 -c MANIFEST.sha256
PYTHON=python3 bash replay.sh "$(mktemp -d)"
```

17 ok, 0 failed, 428 s; exit 0. Every file of `build/` is equal to `record/`, and `MANIFEST.sha256` confirms every file of this folder.

## Files

| file | |
| --- | --- |
| `replay.sh` | downloads, checksums, every script, comparison with `record/` |
| `src/zipget.py` | members of a zip on a web server by HTTP range, without the archive |
| `src/versions.py` | the versions of Python, NumPy and SciPy |
| `src/geometry-tools/mat5load.py` | MAT v5 reader, standard library only |
| `src/forks3d.py` | the reader of the stored tree (paths, turns, fitted lines), shared |
| `src/heat_fork_lib.py` | a leg's stored thickness over a stretch of path, and its stored speed, shared |
| `src/triangle2.py` | section 1: the two balance equations, the exponent of each, bootstrap and shuffles |
| `src/kirchhoff.py` | section 2: the exponent conserved as a number, the current-like sum, the speed law |
| `src/det_current.py` | section 2: speeds at the junction from the raw dots, thickness from the stored fork |
| `src/planes.py` | section 3: rotation between successive stored fork planes, control, lean against the sibling |
| `src/planes_check.py` | section 3: grouping of the stored forks; planes from lines at 2 to 6 mm and end to end |
| `src/planes_azimuth.py` | section 3: the azimuth of the spread against the cameras' axes |
| `src/det_planes.py` | section 3: the rotation on the raw dots, control, by length of the leg |
| `src/det_planes2.py` | section 3: three forks in a row, the hand of the shed branch |
| `src/cloud_forks.py` | lightning: reading a radio map, the growth tree and its forks, shared |
| `src/cloud_planes.py` | section 4: the rotation between successive forks of a flash, control, how the planes lie |
| `record/` | expected output of every script; `data.sha256` for the 50 input files |
| `MANIFEST.sha256` | SHA-256 of every file of this folder |

## References

- Guo and Nijdam, Plasma Sources Sci. Technol. 33, 045006 (2024), [doi:10.1088/1361-6595/ad37bf](https://doi.org/10.1088/1361-6595/ad37bf). Data: [Zenodo 10534905](https://zenodo.org/records/10534905), CC BY 4.0. Only the abstract was read.
- Scholten, Hare, Dwyer, Liu, Strepka, Buitink, Corstanje, Falcke, Huege, Hörandel and co-authors, processed data for "Distinguishing features of High Altitude Negative Leaders as observed with LOFAR" (2021), DataverseNL [doi:10.34894/MGLPXM](https://doi.org/10.34894/MGLPXM), CC0 1.0.
- Scholten, data for figures 2 to 4 of "Small-scale discharges observed near the top of a thunderstorm" (2022), [Zenodo 7394137](https://zenodo.org/records/7394137), CC BY 4.0.
- Murray, J. Gen. Physiol. 9, 835 (1926), [doi:10.1085/jgp.9.6.835](https://doi.org/10.1085/jgp.9.6.835). Not read; cited as reported by Hagmeijer and Venner, [arXiv 1812.09706](https://arxiv.org/abs/1812.09706).
- Sauret, Halson, Brown, Fleming and Bailey, J. Anat. 200, 123 (2002), [PMC1570625](https://pmc.ncbi.nlm.nih.gov/articles/PMC1570625). Read; quoted from it. Kitaoka and co-authors (1999) and Martonen (1995) are cited as reported by Sauret and co-authors.
- Dijcks, van der Leegte and Nijdam, Plasma Sources Sci. Technol. 32, 045004 (2023), [doi:10.1088/1361-6595/acc821](https://doi.org/10.1088/1361-6595/acc821).
- Luque and Ebert, New J. Phys. 16, 013039 (2014), [arXiv 1307.2378](https://arxiv.org/abs/1307.2378).
- Wang, Dijcks, Guo and co-authors, [arXiv 2208.07279](https://arxiv.org/abs/2208.07279). Nijdam and co-authors (2008) and Chen and co-authors (2018) are cited as reported there and in the review below.
- Nijdam, Teunissen and Ebert, Plasma Sources Sci. Technol. 29, 103001 (2020), [arXiv 2005.14588](https://arxiv.org/abs/2005.14588).

Questions: lmtlssss@colony.technology
