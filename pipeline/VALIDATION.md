# Validation: known analogs

Generated 2026-11-15 14:12 UTC. Tiles scored: jezero 142,573, lunar_south_pole 142,573.

## Method

Each known analog is evaluated only where it is a claimed analog, with a rule fixed before looking at the results. **Target** = its body (`analog_for`): Mars → jezero, Moon → lunar_south_pole. **Profiles** = the mission profiles its `used_for` text names, by keyword (an analog can map to several): **rover**: rover, mobility, field operations, instrument, drilling · **geology**: geology, geolog, volcan, mineral, impact, biosignature, life-detection, life detection, astrobiology, habitab · **polar**: polar, permafrost, ice, cold. An analog **succeeds** if its tile is in the top 10% of all scored Earth tiles on at least one of its mapped target × profiles; the method succeeds if more than half of the analogs do. Analogs whose tile is excluded (e.g. vegetated) count as failures. The scores themselves are not changed by this rule, and the weights were not tuned on the analogs.

## Results

| Analog | Analog for | Used for | Mapped profiles | Rank and top % on each mapped target × profile | In top 10%? |
|---|---|---|---|---|---|
| Atacama Desert (Yungay sector), Chile | Mars | Hyperarid soils, extreme dryness and low biomass; testing life-detection instruments and drilling | rover, geology | jezero × rover: 809 / 142,573 (0.6%) ✓<br>jezero × geology: 6,448 / 142,573 (4.5%) ✓ | yes |
| McMurdo Dry Valleys, Antarctica | Mars | Cold hyperarid polar desert, permafrost and microbial survival; habitability and biosignature studies | geology, polar | jezero × geology: 105,997 / 142,573 (74.3%)<br>jezero × polar: 128,274 / 142,573 (90.0%) | no |
| Haughton Impact Crater, Devon Island, Canada | Mars, Moon | Impact-crater geology in a cold polar desert with permafrost; rover operations and subsurface-life studies | rover, geology, polar | jezero × rover: 9,438 / 142,573 (6.6%) ✓<br>jezero × geology: 23,207 / 142,573 (16.3%)<br>jezero × polar: 38,354 / 142,573 (26.9%)<br>lunar_south_pole × rover: 25,112 / 142,573 (17.6%)<br>lunar_south_pole × geology: 126,342 / 142,573 (88.6%)<br>lunar_south_pole × polar: 59,129 / 142,573 (41.5%) | yes |
| Rio Tinto, Spain | Mars | Acidic, iron-rich waters and mineral alteration; extremophile and habitability studies | geology | – (excluded: vegetated tile (NDVI 0.58)) | no (excluded) |
| Kilauea Volcano (summit region), Hawaii, USA | Moon, Mars | Basaltic volcanic terrain and lava features; planetary volcanism and rover field-geology studies | rover, geology | – (excluded: vegetated tile (NDVI 0.42)) | no (excluded) |
| Mojave Desert, California, USA | Mars | Arid terrain and temperature extremes; rover mobility, instrument testing and field operations | rover | jezero × rover: 3,915 / 142,573 (2.7%) ✓ | yes |
| Svalbard, Norway | Mars | Arctic cold, permafrost and ice-related landforms; astrobiology and polar-environment studies | geology, polar | jezero × geology: 141,820 / 142,573 (99.5%)<br>jezero × polar: 139,386 / 142,573 (97.8%) | no |
| University Valley, McMurdo Dry Valleys, Antarctica | Mars | Extremely dry permafrost and ice-cemented ground; subsurface sampling, drilling and habitability studies | rover, geology, polar | jezero × rover: 137,884 / 142,573 (96.7%)<br>jezero × geology: 123,511 / 142,573 (86.6%)<br>jezero × polar: 130,761 / 142,573 (91.7%) | no |
| Moab, Utah, USA | Mars | Desert biological soil crusts and microbial colonization; astrobiology and life-detection research | geology | jezero × geology: 101,230 / 142,573 (71.0%) | no |
| Icelandic volcanic fields (Askja region), Iceland | Mars, Moon | Basaltic volcanic and subglacial landforms; volcanism, ice-rock interactions and planetary field studies | geology, polar | jezero × geology: 105,997 / 142,573 (74.3%)<br>jezero × polar: 43,757 / 142,573 (30.7%)<br>lunar_south_pole × geology: 104,336 / 142,573 (73.2%)<br>lunar_south_pole × polar: 85,197 / 142,573 (59.8%) | no |

**3 of 10 known analogs in the top 10% on at least one of their mapped target × profiles (2 excluded: no valid tile; 3 of the 8 with a valid tile).** Success = more than half: **no**.

Per target: jezero (Mars): 3 of 10 Mars analogs (8 with a valid tile); lunar_south_pole (Moon): 0 of 3 Moon analogs (2 with a valid tile).

Per target × profile (analogs mapped to it, passing on that exact target × profile):

- jezero × rover: 3 of 5 mapped analogs pass (1 excluded)
- jezero × geology: 1 of 9 mapped analogs pass (2 excluded)
- jezero × polar: 0 of 5 mapped analogs pass
- lunar_south_pole × rover: 0 of 2 mapped analogs pass (1 excluded)
- lunar_south_pole × geology: 0 of 3 mapped analogs pass (1 excluded)
- lunar_south_pole × polar: 0 of 2 mapped analogs pass

## Limitations of this validation

- The keyword mapping is mechanical: e.g. "drilling" maps University Valley to rover, "ice-rock interactions" maps Iceland to polar. It was fixed before the results and not edited afterwards.
- Our dimensions do not measure ground ice or permafrost, which is what polar analogs (McMurdo, University Valley, Svalbard) are mostly used for.
- Earth polar sites have a 1–2.5 °C mean day–night range (McMurdo 1.5, University Valley 1.4, Svalbard 2.4 °C: the Sun barely moves in their sky) vs 65 °C at Jezero, and mean nights no colder than about −35 °C vs −84 °C: they are cold, but not Jezero-like. This is why the polar analogs fail on jezero × polar.
