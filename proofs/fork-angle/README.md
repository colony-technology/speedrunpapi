# Fork angle: streamer forks in three dimensions

The opening between the two daughters of a streamer fork, measured on a public record of laboratory discharges in three dimensions.

Record: Guo and Nijdam, Plasma Sources Sci. Technol. 33, 045006 (2024), [doi:10.1088/1361-6595/ad37bf](https://doi.org/10.1088/1361-6595/ad37bf). Data: [Zenodo 10534905](https://zenodo.org/records/10534905), CC BY 4.0. 24 runs in air at 133 to 200 mbar and in nitrogen with 1 to 5 percent oxygen. Each discharge is stored as one path, or as a parent and two daughters; points in millimetres.

The data is not in this repository. `replay.sh` fetches the 24 `DataExp.mat` tree files from Zenodo by HTTP range out of `Experiments.zip` (877,340,999 B), 21 MB in all, and checks them against `record/data.sha256`. They are read as data by `src/geometry-tools/mat5load.py`, a MAT v5 reader on the Python standard library.

```
689 forks, both daughters at least 16 mm

at the fork, two readings
  record's own stored fork angle            87.1 degrees, quartiles 79.8 and 98.8
                                            Branchplane.Angle = Gamma1 - Gamma2, as stored by the authors
  tangents of the stored arcs, first points 75.6 degrees, quartiles 70.2 and 82.1
  between them                              rank correlation 0.943; why they differ is open, the question for the authors
closing                                     about 2 degrees per mm from the first stored points on
                                            0.87 of (opening at 3 to 5 mm) / (distance left to the plate)
                                            rank correlation 0.946, 398 forks; distance left = 67.3 - z - 9 mm, z the height of the fork
2 pi / 5                                    not singled out
```

**Corrected 15 November 2026.** The first version of this page said "born at 72 to 75 degrees". That is the angle between the tangents of the stored arcs at the stored fork points. The record's own angle for the same forks is 87 degrees, which that version had not read.

2 pi / 5 = 72.0 degrees is the angle derived for a tip that splits while following a harmonic field in the plane, and measured there on nearly 5,000 forks of rivers fed by seepage, 71.9 +/- 0.8 (Devauchelle, Petroff, Seybold, Rothman 2012).

## Every stored path is the authors' fit

`src/forks3d_arc.py`, 1,421 daughters of at least 16 mm. The turning per mm is the same in the first, middle and last third of every path (median 1.011 degrees per mm). Its spread along a path is 0.0000 of its mean, and no point leaves the path's own plane (0.00000 mm). The paths are exact circular arcs in a plane.

So every reading on this page is a reading of the authors' circular fits, not of raw detections. The straightness of the closing in path distance and the agreement of the carried-back opening between stretches follow from the arcs being circles. They are not independent tests.

## The record's own angle

`src/forks3d_own.py`. Each forked discharge has an entry `Branchplane` with `Angle` = Gamma1 - Gamma2. For the 689 forks with both daughters at least 16 mm:

| condition | forks | stored Angle, median (quartiles) | the arcs at their own first points |
| --- | --- | --- | --- |
| air, 133 mbar, 10 kV | 44 | 94.8 (86.2, 108.0) | 79.3 |
| air, 133 mbar, 7 kV | 75 | 86.4 (79.4, 94.4) | 76.1 |
| air, 133 mbar, 9 kV | 206 | 86.2 (80.7, 98.7) | 77.2 |
| air, 167 mbar, 11 kV | 152 | 89.3 (79.5, 99.7) | 75.9 |
| air, 200 mbar, 13 kV | 160 | 85.7 (79.3, 96.8) | 73.8 |
| nitrogen with 5 percent oxygen | 45 | 86.0 (75.2, 98.8) | 73.4 |
| all | 689 | 87.1 (79.8, 98.8) | 75.6 (70.2, 82.1) |

The stored Angle and the arcs at their first points go together at rank correlation 0.943, with a median difference of 11.6 degrees (quartiles 8.3 and 17.0). The two daughters' first stored points lie 0.97 mm apart (median), so the stored arcs start at the fork. How and where the authors' Angle is taken the record does not say. Why it is 11.6 degrees wider than the tangents of the stored arcs there is not known to us: it depends on how Gamma1 and Gamma2 are defined. `record/own.txt` also prints, for each condition, 11.6 degrees restated as millimetres at the arcs' 2.05 degrees per mm; no split lies there and the page does not use it. The paper gives 80 to 96 degrees in air; its tables are not recomputed here.

## The reader and its control

`src/forks3d.py`. A direction is a line fitted through a stretch of path (its principal axis), pointing along the growth. The opening is the angle between the two daughters' lines in the same stretch. The tangent at the fork (`at0`) is taken from a curve of second degree in path length fitted from 1.5 to 12 mm and carried back to 0.

Control, `forks3d.py --control`: 300 drawn forks per case, points every 0.8 mm with 0.15 mm of scatter, each fork turned at random in space.

| drawn | straight, 2 to 6 mm | bent back 20, 2 to 6 mm | 4 to 10 mm | 8 to 16 mm | bent back 20, tangent carried back to the fork |
| --- | --- | --- | --- | --- | --- |
| 43 | 42.7 | 38.7 | 35.2 | 28.5 | 44.4 |
| 60 | 60.2 | 55.9 | 51.9 | 45.5 | 60.5 |
| 72 | 72.3 | 67.6 | 63.9 | 57.7 | 72.8 |
| 90 | 89.8 | 85.4 | 81.7 | 75.6 | 90.3 |

Straight forks read to 0.3 degrees. On bent forks the stretch readings fall with distance and the tangent carried back reads the drawn angle to 1.4 degrees.

The record: 2,643 discharges, 728 forks with both daughters at least 10 mm, 689 with both at least 16 mm. The stored streamer diameter near the fork is 2.55 mm (median, `forks3d_profile.py`).

## The closing and the place in the gap

The same 689 forks read in successive stretches of path (`forks3d_profile.py`):

| stretch of path from the fork, mm | 0.5 to 2 | 1 to 3 | 2 to 4 | 3 to 5 | 4 to 6 | 5 to 8 | 6 to 10 | 8 to 12 | 10 to 14 | 12 to 16 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| forks with at least 3 points there | 113 | 282 | 420 | 398 | 398 | 683 | 689 | 689 | 689 | 689 |
| opening, median | 71.6 | 70.4 | 68.7 | 67.2 | 65.4 | 62.1 | 58.4 | 54.3 | 50.2 | 46.2 |

The forks start wide and close with distance, about 2 degrees per millimetre at the median.

`forks3d_where.py`, `forks3d_balance.py`, `forks3d_ride.py`: forks with both daughters at least 16 mm and both stretches present, 398. The closing is the opening at 3 to 5 mm less the opening at 12 to 16 mm, per mm. z is the height of the parent's last point. The discharges start near z = -5 at the pin, and the stored paths end at z = 67.3 (99.5th percentile of all stored z, taken as the plate).

| condition | forks | median z of the forks | z under 22: forks, opening, closing | z 22 to 30 | z over 30 |
| --- | --- | --- | --- | --- | --- |
| air, 133 mbar, 7 kV | 75 | 35.5 | 5, 62.6, 1.47 | 16, 66.2, 1.78 | 54, 67.7, 2.84 |
| air, 133 mbar, 9 kV | 146 | 23.4 | 61, 66.6, 1.34 | 48, 68.3, 1.79 | 37, 72.0, 2.73 |
| air, 167 mbar, 11 kV | 72 | 29.8 | 18, 61.5, 1.39 | 19, 66.7, 1.90 | 35, 70.3, 2.65 |
| air, 200 mbar, 13 kV | 77 | 28.4 | 17, 62.3, 1.43 | 26, 66.2, 1.87 | 34, 68.8, 2.43 |
| nitrogen with 5 percent oxygen | 22 | 27.4 | 8, 62.8, 1.34 | 5, 66.4, 1.89 | 9, 68.9, 2.52 |

Rows: the conditions with at least 15 such forks, 392 of the 398.

- Rank correlation of z with the closing: +0.880 on the 398 forks (+0.878 on the 146 of air, 133 mbar, 9 kV). No shuffle of 4,000 comes near.
- One straight line for all conditions: closing = 0.168 + 0.0717 z degrees per mm. What is left over per condition, in the order of the table: -0.18, +0.06, -0.06, -0.09, -0.06.
- At 133 mbar the closing from 1 to 16 mm falls as the voltage rises: 2.30, 1.71, 1.17 degrees per mm at 7, 9, 10 kV (`forks3d_cond.py`). That trend is the place: at 7 kV the forks sit at a median z of 35.5, at 9 kV at 23.4.
- Fork by fork, the closing is 0.87 of (opening at 3 to 5 mm) / (67.3 - z - 9), quartiles 0.82 and 0.92, rank correlation 0.946. It is a relation between the fitted arcs' curvature, their opening and their place in the gap, across 398 forks.
- The opening at 3 to 5 mm itself rises with z: 66.5, 68.3, 72.0 in the three thirds of air, 133 mbar, 9 kV (rank correlation +0.355). Thicker daughters go with a slightly wider fork: 66.4, 68.6, 70.2 by thirds of the stored diameter. Their speed does not (0.000).

## The opening carried to the stored fork points

These are the points where the stored arcs start; there the record's own angle is 87.1 and the arcs' tangents are 75.6 apart (The record's own angle, above). The opening carried to them is a reading of the arcs, not of the split. Because the paths are circles, the agreement between stretches below follows from the arcs and is not an independent test. The tables and the control below measure the opening carried to the stored fork points, and nothing more.

`forks3d_scan.py`. The opening with the closing by the outside field taken off, carried back to the parent's last stored point.

Method, one free number. Along a fork the opening A is taken to fall as (distance left to the plate)^p, so

```
A0 = A(stretch) x ((Z - z_fork) / (Z - z_stretch))^p
```

is the opening carried to the stored fork point, z_stretch being the mean height of the two daughters in the stretch. p is fixed where the medians of A0 from the stretches of the same forks agree best (scan 0.6 to 2.0 in steps of 0.01). Nothing is chosen by eye. The carried-back opening is the mean of those medians.

| plate Z, mm | stretches | forks | best p | spread left | medians of A0 by stretch | carried-back opening |
| --- | --- | --- | --- | --- | --- | --- |
| 66.0 | 1 to 16 mm, five | 200 | 1.20 | 0.14 | 72.0, 71.9, 72.0, 71.9, 72.1 | 72.0 |
| 66.0 | 3 to 16 mm, four | 398 | 1.22 | 0.15 | 72.2, 72.1, 72.1, 72.1 | 72.1 |
| 67.3 | five | 200 | 1.24 | 0.26 | 72.0, 71.9, 71.9, 71.7, 71.8 | 71.9 |
| 67.3 | four | 398 | 1.28 | 0.10 | 72.2, 72.2, 72.2, 72.3 | 72.2 |
| 69.0 | five | 200 | 1.32 | 0.11 | 72.0, 72.0, 72.1, 72.0, 72.0 | 72.0 |
| 69.0 | four | 398 | 1.35 | 0.12 | 72.3, 72.2, 72.1, 72.2 | 72.2 |

The five stretches: 1 to 3, 3 to 5, 5 to 8, 8 to 12, 12 to 16 mm. The four leave out the first.

Bootstrap of the 398 forks (1,000 resamples, Z = 67.3, four stretches): carried-back opening 72.2 (2.5th to 97.5th percentile 71.2 to 73.2); p 1.28 (1.24 to 1.31).

Fork by fork (mean of each fork's four carried-back stretches, p = 1.28): median 72.3, quartiles 68.0 and 76.4. Within 5 degrees of 72: 0.575; of 60: 0.118; of 90: 0.058. Counts in 5-degree bins from 40: 0, 1, 3, 7, 40, 92, 122, 80, 27, 21, 2, 1, 0, 1.

| by condition | forks | carried-back opening |
| --- | --- | --- |
| air, 133 mbar, 7 kV | 75 | 74.6 |
| air, 133 mbar, 9 kV | 146 | 72.8 |
| air, 167 mbar, 11 kV | 72 | 70.5 |
| air, 200 mbar, 13 kV | 77 | 70.1 |
| nitrogen with 5 percent oxygen | 22 | 68.4 |

| by place | forks | carried-back opening |
| --- | --- | --- |
| z under 22 mm | 110 | 68.5 |
| z 22 to 30 mm | 116 | 71.6 |
| z over 30 mm | 172 | 75.7 |

Control, `forks3d_scan_control.py`: 400 drawn forks per case, birth angle drawn around 60, 72 or 85 with 6 degrees of spread, at heights 5 to 50 mm in the same gap, points every 0.7 mm with 0.1 mm of scatter. The 102 to 124 forks per case with at least 3 points in each stretch are read by the same four stretches and the same scan. The closing rule is not told to the reader.

| closing rule of the drawn forks | drawn 60 reads | drawn 72 reads | drawn 85 reads | straight-line way (below): 60, 72, 85 read |
| --- | --- | --- | --- | --- |
| power 0.8 of the distance left | 62.4 | 73.1 | 85.0 | 60.9, 72.9, 85.6 |
| power 1.3 | 58.2 | 70.9 | 85.7 | 58.2, 70.7, 84.7 |
| power 1.8 | 61.9 | 72.4 | 86.8 | 60.4, 69.4, 84.1 |
| a fixed 1.2 degrees per mm | 56.9 | 71.9 | 82.9 | 58.2, 72.2, 84.6 |
| straight for the first 4 mm, then power 1.3 | 69.5 | 80.5 | 95.5 | 69.0, 80.8, 95.5 |

The method follows the drawn angle to about 3 degrees and does not pull toward 72, as long as the closing starts at the fork. If a fork keeps its birth angle for its first millimetres, the method reads about 9 degrees high.

**Two stored fork points.** A second way of carrying back assumes no law for the closing (`forks3d_line.py`): a straight line through each fork's four openings against path distance, carried to distance 0. It gives 74.6 (quartiles 70.1 and 80.6; bootstrap of the median 74.0 to 75.4), and the same from the three nearer stretches (74.6) as from the three farther (74.5). Between 3 and 16 mm the closing is as straight in path distance (1.95, 1.95, 1.82 degrees per mm) as it is a power of the distance left; on circular arcs both follow.

On the drawn forks the two ways agree to within 3.0 degrees, 0.6 in the median case (last column of the control table). On the record they differ by 2.4 because they carry back to different points (`forks3d_line2.py`). The law above carries to the parent's last stored point, the straight line to the daughters' first stored points, and the first lies a median of 0.86 mm (quartiles 0.48 and 1.56, mean 1.07) beyond the second along the gap. The same power law carried to the daughters' first points gives 74.4, 74.5, 74.5, 74.7. So the two ways agree.

## What the record says, then

At the fork the record gives two readings that differ. Its own stored fork angle is 87.1 degrees. The tangents of its own stored arcs at their first points are 75.6 apart (and about 72 at the height of the parent's last stored point, 0.9 mm on). From there the arcs close at about 2 degrees per mm, to 46 at 14 mm. Nothing marks 72 on the way.

## What is withdrawn

"Born at 72 to 75 degrees" as the fork's birth angle, and the comparison with 2 pi / 5: the record's own number for the same forks is 87. The scan above and its control measured correctly the opening of the stored arcs carried to the stored fork points.

## What stands

- The closing: 0.87 of the opening at 3 to 5 mm over the distance left to the plate, rank correlation 0.946, the same in five conditions. It is a relation between the fitted arcs' curvature, their opening and their place in the gap, across 398 forks.
- The three legs (below): the daughter that turns less is the thicker in 0.887 of forks and the faster in 0.897; rank correlation +0.621 between the division read from the turns and the stored thickness ratio. These use turns at 3 to 5 mm and do not depend on where the split is placed.
- The reader and its controls.
- The thin-channel closed form (below) as a statement about its model: 61.8 to 79.9 degrees for uniform charges. It holds the arcs' tangents at the fork (75.6) and not the authors' stored angle (87.1); its own first solved-charge attempt pointed near 90 for long thin forks and was set aside as unreliable. The charges solved on a real surface are not yet computed; until then the reckoning decides nothing between the two readings.
- The forward reckoning of the three legs (below) gave an opening of 71.4 from the three thicknesses: 4 degrees under the arcs' tangents at the fork and 16 under the authors' stored angle. Its claim to the opening is withdrawn with the carried-back one; its turns stand as measured.
- The junction balance, what the fork conserves, and the turn between successive fork planes, on the same record and its raw detections: `proofs/spark-tree/`.

## A first reckoning in three dimensions, for thin channels

`src/fork3d_theory.py`. Every derivation of 2 pi / 5 is for the plane. In space the thin-needle argument of the plane does not carry over as it stands: a thin line has no capacity there. What can be reckoned directly follows.

Setting. A thin conducting parent ends at a point and continues as two thin straight daughters of length l at half the opening, alpha / 2, to each side, all in one plane. Thin channels carry their charge as line charges on their axes: lambda0 per length on the parent near the fork, kappa x lambda0 on each daughter, taken uniform. A tip keeps its direction when the field across its own axis at the tip is zero. Its own straight leg gives none there. The parent's charge pulls the tip back toward the parent's line (the field of a half-line of charge at the tip points at half the tip's own angle). The other daughter pushes it away.

Closed form, in units of lambda0 / (4 pi eps0 l), checked against direct summation of the line charges to 2 parts in 10,000 at five angles:

```
T(alpha, kappa) = -tan(alpha / 4) + kappa [ cot(alpha) (sin(alpha / 2) + cos(alpha)) - cos(alpha / 2) + sin(alpha) ]
```

The fork holds where T = 0.

| kappa: each daughter's charge per length over the parent's | 0.50 | 0.60 | 0.70 | 0.75 | 0.80 | 0.90 | 1.00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| opening that holds, degrees | 61.77 | 66.24 | 70.19 | 72.01 | 73.74 | 76.96 | 79.90 |

72 degrees holds at kappa = 0.74965. Between the two natural ends (the parent's charge per length shared between the daughters, kappa 1/2; each daughter as charged per length as the parent, kappa 1) the opening runs from 61.8 to 79.9 degrees. The band holds the arcs' tangents at the fork (75.6) and not the record's own stored angle (87.1); the first solved-charge attempt pointed near 90 (below). The charges solved on a real surface are not yet computed; until then the reckoning decides nothing between the two readings.

**What this is and is not.** It is an exact statement about a model: thin straight legs, uniform line charges, the outside field's own pull across the tip left out (small for a parent long against the daughters). It does not single out 72; it says a fork in space holds somewhere in a band of about 18 degrees set by how the charge divides. Not done: the charges solved for one potential on a real surface (a first try with line segments failed at the junction and pointed near 90 degrees for long thin forks); channels that are not at one potential, which a streamer's are not, its charge sitting mostly in the head; whether the literature has this closed form (not searched).

## The fork as one move with three legs

`src/heat_fork.py`, `src/heat_kernel.py`.

**The mapping.** A fork is one move with three legs: the parent, the daughter that keeps nearer the parent's line (strong), and the one that turns further (weak). Each leg gets one number, the charge it carries per length: kappa for a daughter, in units of the parent's. The thin-channel reckoning above, taken with two unequal daughters (`heat_fork.py`): each tip keeps its direction when

```
tan(h_weak / 2) = kappa_strong G(alpha),   tan(h_strong / 2) = kappa_weak G(alpha),   alpha = h_strong + h_weak
G(alpha) = cot(alpha) (sin(alpha / 2) + cos(alpha)) - cos(alpha / 2) + sin(alpha)
```

Each daughter's turn h is set by the other daughter's charge per length: the less charged one is pushed further out. So the two angles of a fork read two charges per length, and the two charges give the two angles.

**Read from the angles** (398 forks, turns at 3 to 5 mm, medians with quartiles; `record/heat-fork.txt`): turn strong 18.8 (11.0, 25.4), turn weak 48.9 (41.2, 56.5); kappa strong 0.957 (0.745, 1.211), kappa weak 0.334 (0.195, 0.479). The parent's line lies between the daughters (sum of turns over opening: 1.000).

**The witness the angles never saw**: each leg's stored thickness D and speed V. Strong over parent: thickness 0.885 (0.737, 1.053), speed 1.016. Weak over parent: thickness 0.593 (0.505, 0.709), speed 0.797. The daughter that turns less is the thicker one in 0.887 of forks and the faster one in 0.897. Rank correlations fork by fork, none of 2,000 shuffles as far unless stated:

| | rank correlation |
| --- | --- |
| kappa weak / kappa strong from the angles, against thickness weak / strong | +0.621 |
| kappa weak, against speed weak / parent | +0.597 |
| turn weak, against thickness weak / strong | -0.562 |
| kappa weak, against thickness weak / parent | +0.331 |
| kappa strong, against thickness strong / parent | +0.283 |
| kappa strong, against speed strong / parent | +0.121 (0.015 of shuffles as far) |

**Forward** (`heat_kernel.py`, `record/heat-kernel.txt`): the three thicknesses in, the fork out, no free number. "Strong" is taken as the thicker daughter, so that no angle is used.

| charge per length taken as | predicted opening | predicted turns, thicker and thinner | measured |
| --- | --- | --- | --- |
| thickness | 71.4 | 29.2 and 42.5 | opening at the fork: 87.1 by the record's own stored angle, 75.6 by the arcs' tangents; turns 18.8 and 48.7 at 3 to 5 mm |
| thickness squared | 64.9 | 20.6 and 44.0 | (opening at 3 to 5 mm: 67.2) |

With charge per length as thickness the predicted opening, 71.4, is 4 degrees under the arcs' tangents at the fork and 16 under the authors' stored angle; its claim to the opening is withdrawn. Fork by fork it gets the turns: rank correlation of predicted against measured +0.502 for the thicker daughter and +0.491 for the thinner, +0.507 and +0.466 with thickness squared. It does not get the scatter of the opening itself (-0.043, 0.427 of shuffles as far).

**The move before** (the parent's own thickness and speed): a parent that forks is thicker than an unforked discharge of the same condition in 0.805, 0.733, 0.722, 0.725, 0.714 of pairs (five conditions). Its speed does not separate them in one direction (0.012 to 0.512). Opening against the parent's thickness: rank correlation +0.165 (0.001).

**Stated plainly.** In this record the two turns of a fork and the stored thickness and speed of its three legs agree: from the two turns alone, the strong daughter carries about the parent's charge per length (0.96) and the weak one a third (0.33); the daughter that turns less is the thicker in 0.887 of forks and the faster in 0.897, and the division read from the turns goes with the stored thickness ratio at rank correlation +0.621. These use turns at 3 to 5 mm and do not depend on where the split is placed. The claim to the opening is withdrawn: from the three thicknesses the opening comes out at 71.4, 4 degrees under the arcs' tangents at the fork and 16 under the authors' stored angle. The reckoning is for thin legs with uniform charge (the limits of the thin-channel reckoning apply).

## Replay

```sh
PYTHON=python3 bash replay.sh /path/to/new/data/dir     # Python 3 with NumPy, network to zenodo.org; exit 0 when every check holds
```

| step | what | expected |
| --- | --- | --- |
| 1 | `src/zipget.py`: the 24 `DataExp.mat` members of `Experiments.zip` into the named directory | 24 files, equal to `record/data.sha256` |
| 1a | `src/forks3d_arc.py`, `src/forks3d_own.py` on the directory | equal to `record/arc.txt`, `record/own.txt`, line for line |
| 2 | `src/forks3d.py --control`, `src/forks3d_scan_control.py` | equal to `record/control.txt`, `record/scan_control.txt`, line for line |
| 3 | `src/forks3d.py`, `forks3d_profile.py`, `forks3d_cond.py`, `forks3d_where.py`, `forks3d_balance.py`, `forks3d_ride.py`, `forks3d_birth.py`, `forks3d_scan.py` on the directory | equal to `record/`, line for line |
| 4 | `src/forks3d_line.py`, `src/forks3d_line2.py` on the directory; `src/fork3d_theory.py` | equal to `record/line.txt`, `record/line2.txt`, `record/theory.txt`, line for line |
| 5 | `src/heat_fork.py`, `src/heat_kernel.py` on the directory | equal to `record/heat-fork.txt`, `record/heat-kernel.txt`, line for line |

Every random draw is seeded. Output goes to `build/`. Nothing in the data directory is run.

Recorded run: 15 November 2026, Apple M1, macOS 27.2, Python 3.11.18, NumPy 2.4.6. A fresh clone of this branch into a new temporary directory, with the 24 files of an earlier download from Zenodo the same day, checked against `record/data.sha256`:

```sh
T=$(mktemp -d)
git clone REPOSITORY "$T/speedrunpapi"
cd "$T/speedrunpapi/proofs/fork-angle" && shasum -a 256 -c MANIFEST.sha256
PYTHON=python3 bash replay.sh DATA_DIR
```

21 ok, 0 failed, 39 s; exit 0. Every file of `build/` is equal to `record/`, and `MANIFEST.sha256` confirms every file of this folder. The run before this correction fetched the files fresh: 19 ok, 0 failed, 88 s.

## Files

| file | |
| --- | --- |
| `replay.sh` | download, checksums, every script, comparison with `record/` |
| `src/zipget.py` | members of a zip on a web server by HTTP range, without the archive |
| `src/geometry-tools/mat5load.py` | MAT v5 reader, standard library only |
| `src/forks3d_arc.py` | every stored daughter path against a circular arc in a plane |
| `src/forks3d_own.py` | the record's own stored fork angle (`Branchplane.Angle`) beside the stored arcs, by condition |
| `src/forks3d.py` | the reader, the 728 forks, `--control` |
| `src/forks3d_profile.py` | opening by stretch of path, stored diameter |
| `src/forks3d_cond.py` | opening by stretch and condition, turns from the parent's line |
| `src/forks3d_where.py` | closing by place in the gap, the line against z |
| `src/forks3d_balance.py` | closing and opening against place, diameter and speed, rank correlations with shuffles |
| `src/forks3d_ride.py` | the plate, closing against opening over distance left |
| `src/forks3d_birth.py` | carry-back with the power fixed at 0.87, stretch by stretch |
| `src/forks3d_scan.py` | the scan of p, the bootstrap, by condition and place |
| `src/forks3d_line.py` | the opening carried to the stored fork points by a straight line through each fork's openings, no law for the closing |
| `src/forks3d_line2.py` | both ways from nearer and farther stretches; the two stored fork points |
| `src/forks3d_scan_control.py` | the scan and the straight-line way on drawn forks of known birth angle |
| `src/fork3d_theory.py` | thin channels in space: the closed form against direct summation, the opening that holds by kappa |
| `src/heat_fork.py` | three legs: charges per length read from the two turns, against stored thickness and speed; the move before |
| `src/heat_kernel.py` | three legs forward: the stored thicknesses in, opening and turns out |
| `record/` | expected output of every script; `forks3d.tsv`, one line per fork, derived from the record (CC BY 4.0, Guo and Nijdam) |
| `MANIFEST.sha256` | SHA-256 of every file of this folder |

## References

- Guo and Nijdam, Plasma Sources Sci. Technol. 33, 045006 (2024), [doi:10.1088/1361-6595/ad37bf](https://doi.org/10.1088/1361-6595/ad37bf). Data: [Zenodo 10534905](https://zenodo.org/records/10534905), CC BY 4.0.
- Devauchelle, Petroff, Seybold and Rothman, Proc. Natl. Acad. Sci. USA 109, 20832 (2012), [doi:10.1073/pnas.1215218109](https://doi.org/10.1073/pnas.1215218109).

Questions: lmtlssss@colony.technology
