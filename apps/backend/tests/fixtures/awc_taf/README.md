Real TAF of SACO (Córdoba/Taravella) from the Aviation Weather Center (NOAA, public domain), captured on 2026-10-06 from `https://aviationweather.gov/api/data/taf?ids=SACO&format=json` (no `hours` parameter: with `hours=24` AWC answers HTTP 400). Unmodified.

| File | Raw TAF | Periods |
|---|---|---|
| `SACO.json` | `TAF SACO 061700Z 0618/0718 05015KT 9999 SCT035 TX28/0719Z TN14/0710Z BECMG 0623/0702 02005KT 9999 BKN035 FEW040TCU BECMG 0703/0706 02005KT 7000 BKN030 PROB40 TEMPO 0706/0709 18010KT 7000 SCT015 OVC020 BECMG 0712/0715 29015KT 9999 SCT030 FEW040TCU` | 5: initial, BECMG x3, TEMPO with probability 40 |

Three more real Argentine TAFs, captured the same day from the same endpoint, unmodified, one entry each: `SARI.json` (PROB30 with CAVOK, which AWC sends as `NSC` + `NSW`, then a BECMG to `0500 FG OVC005`), `SASA.json` (VRB wind, `PROB40 TEMPO` with mist) and `SAAR.json` (a TEMPO with gusts whose visibility is an empty string and whose clouds are empty, then TSRA with CB).

Values seen in 15 real Argentine TAFs (56 periods): `fcstChange` null, `TEMPO`, `BECMG` and `PROB` (alone, with probability 30 or 40); `visib` as `"6+"`, a number, or an empty string; `wdir` as an integer, `null` or `"VRB"`; `wxString` such as `TSRA`, `-RA -DZ`, `FG`, `BR` or `NSW`; clouds `NSC`, `FEW` with type `CB` or `TCU`.

Shapes worth knowing: `visib` is a string (`"6+"`) or a number of statute miles (`4.35` = 7000 m); `wdir` is an integer, or the string `"VRB"` for variable wind (see `SASA.json`); `wxString` is `null` or a space-separated string (`"-RA BR"`); TX/TN come in `temp[]` of the first period.
