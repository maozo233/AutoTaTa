<p align="center"><img src="assets/app-icon.png" width="132" height="132" alt="AutoTaTa" /></p>
<h1 align="center">AutoTaTa</h1>
<p align="center">An unofficial automation tool for 塔塔冒险队, played on an Android emulator on Windows.<br />Connect via ADB or the MuMu SDK for lineup deployment, treasure hunting, rafting and fishing.</p>
<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong> &nbsp;·&nbsp; <a href="#interactions">Interactions</a> &nbsp;·&nbsp; <a href="docs/KNOWN_ISSUES.en.md">Known issues</a></p>

<p align="center"><a href="docs/media/home.png"><picture><source media="(max-width: 600px)" srcset="docs/media/home.png" /><img src="docs/media/cover-en.svg" width="75%" alt="Full AutoTaTa home window with entries for Lineup, Fishing, Treasure and Rafting" /></picture></a></p>

## Why AutoTaTa?

Copying a formation means switching between a guide and the emulator, finding each character in the inventory and checking its position. Fishing keeps players watching the float. Rafting asks them to choose between the same rewards round after round. With AutoTaTa, players can supply a formation image, rank the rewards they want and set spending limits up front. That leaves fewer trips back to the guide, fewer repeated clicks and more time for the adventure itself.

**Windows · 0.2.36 · Maintenance ended**　Select a window to view it at full resolution.

<table>
  <tr>
    <td width="50%" align="center" valign="top"><div><a href="docs/media/lineup.png"><img src="docs/media/preview-lineup.svg" width="75%" alt="Lineup" /></a></div><strong>Lineup</strong><br />Deploy a shared formation and correct individual tiles.</td>
    <td width="50%" align="center" valign="top"><div><a href="docs/media/fishing.png"><img src="docs/media/preview-fishing.svg" width="75%" alt="Fishing" /></a></div><strong>Fishing</strong><br />Automate casting and coordinate bait use with teammates.</td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top"><div><a href="docs/media/treasure.png"><img src="docs/media/preview-treasure.svg" width="75%" alt="Treasure" /></a></div><strong>Treasure</strong><br />Read the live board and compare the odds on unopened tiles.</td>
    <td width="50%" align="center" valign="top"><div><a href="docs/media/rafting.png"><img src="docs/media/preview-rafting.svg" width="75%" alt="Rafting" /></a></div><strong>Rafting</strong><br />Adjust the boat multiplier and drag rewards into priority order.</td>
  </tr>
</table>

## Interactions

Each of the four loops opens on the full 0.2.36 window and follows one action. All four were captured offline with a sample lineup and board.

### Lineup · Deploy a team from a shared formation

Paste a screenshot from a guide or a formation shared by another player. AutoTaTa identifies characters by their appearance at different evolution stages and reads their positions. It checks the team already on the board, keeps characters that are in place, withdraws unwanted characters blocking a destination, moves retained characters to their target tiles, withdraws any remaining extras and fills the gaps from inventory. If the exact stage is missing, a character from the same evolution line can stand in.

A question mark flags an uncertain match. Once the run has stopped, select the tile to choose a character or mark it empty. The loop shows the player clearing the tenth tile.

<p align="center"><a href="docs/media/interaction-lineup.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/media/lineup.png" /><img src="docs/media/interaction-lineup.png" width="383" alt="The rightmost question mark in row two opens the editor. Choosing Set empty clears that tile." /></picture></a></p>

Both 5×5 and 3×4 formations need the entire friendly board. Crop out opponents and buttons from a wide screenshot. If a row is already missing from a five-row board, capture it again, even if that row was empty. [Lineup guide (Chinese)](docs/USAGE.md#一键上阵第一版)

### Treasure · Compare the odds before digging

Live recognition reads the emulator through the MuMu SDK. The solver uses treasure silhouettes to infer their shapes and sizes, then combines those with revealed empty tiles and known treasure cells to calculate the chance of a hit on each unopened tile. It updates the odds when it confirms a change on the board. The player chooses where to dig.

Players can also correct a tile or adjust the treasure configuration. In the demo, marking the recommended center tile as empty changes the odds across the board and shifts the recommendation to four surrounding tiles.

<p align="center"><a href="docs/media/interaction-treasure.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/media/treasure.png" /><img src="docs/media/interaction-treasure.png" width="510" alt="The center tile changes from a 44% recommendation to empty. Four surrounding tiles now show 45%." /></picture></a></p>

### Rafting · Set the boat multiplier and rank rewards

Players can change the boat multiplier during a run. The new setting applies before the next spin. Rewards are ranked from left to right. In the demo, dragging the third card to the front makes it the first choice whenever it appears in a three-way offer. Once the boat budget is set, the assistant handles spins and reward collection. Free spins do not spend that budget, and a boat purchase prompt stops the run.

<p align="center"><a href="docs/media/interaction-rewards.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/media/rafting.png" /><img src="docs/media/interaction-rewards.png" width="428" alt="The third reward card moves to the front and the previous first and second cards shift right." /></picture></a></p>

### Fishing · Set a rod budget and share baiting duties

The assistant casts and plays the fish automatically. With automatic baiting enabled, it checks the rod grade and current luck to decide whether to scatter bait for the team. When luck falls short, it gives teammates time to act. If they restore full luck, it skips its turn. If luck is still low when the wait ends, it checks the local bait supply and budget before scattering more.

Rod and bait use are tracked separately. The demo changes the rod budget from 0 (unlimited) to 30. The counter below updates to 0 / 30 rods used.

<p align="center"><a href="docs/media/interaction-fishing.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/media/fishing.png" /><img src="docs/media/interaction-fishing.png" width="424" alt="In the full fishing window, changing the rod budget from 0 (unlimited) to 30 updates the counter to 0 / 30." /></picture></a></p>

## Design decisions

- **Organize the home screen around player goals.** Lineup, Fishing, Treasure and Rafting each open directly to their own settings, status and stop button. Players can adjust a run on the page where they started it. [Home screen](docs/media/home.png)
- **Show what each setting changes.** The fishing window labels the rod budget, explains that 0 means unlimited and shows rods used against the cap. The rafting window makes priority visible by putting rewards in a row. Dragging a reward left raises its priority. [Fishing screen](docs/media/fishing.png)
- **Put the correction where the mistake appears.** A question mark on the lineup board opens the character editor. On the treasure board, marking a tile as empty or occupied updates the probabilities in place. [Cell editor](docs/media/lineup-editor.png) · [Treasure screen](docs/media/treasure.png)

## Design & implementation

AutoTaTa explores how AI can contribute to product design and development. The designer defined the scope, interaction flows and visual system. Starting from an AI draft, the designer revised layouts, typography and component states in Figma, then checked them in the running Windows app. AI assisted with QML and Python implementation, failure analysis and regression checks. The designer reviewed the outcomes and decided where uncertainty should interrupt automation. [Design process (Chinese)](docs/DESIGN_AND_AI.md)

The UI uses Qt Quick and PySide6. Local image matching and OCR read the game screen. Lineup deployment checks character identity, position and count. The treasure solver enumerates layouts consistent with the player's marks and labels its results as estimates when it switches to sampling. [UI components](assets/ui) · [Lineup implementation](lineup) · [Treasure solver](treasure/solver.py)

## Results, known issues & status

Forty records from two machines contained 25 distinct source images. Replaying that set reduced uncertain cells **from 12 to 8** while preserving previously confirmed identities. Version 0.2.36 passed **197 lineup regression checks**. End-to-end deployment in the game was still awaiting a retest when maintenance ended. [Validation notes (Chinese)](docs/VALIDATION_SUMMARY.md)

- **Lineup** can miss or misidentify characters. Typing in the manual editor sometimes fails to narrow the candidate list.
- **Treasure** can misread the board. Presets cover stages 1–24, but higher stages lack continuous in-game testing.
- **Some dropdowns** let a click reach the control underneath. [All known issues](docs/KNOWN_ISSUES.en.md)

The last functional update was **October 24, 2026**. Maintenance ended on **October 28, 2026** due to time constraints and the designer no longer playing the game. Version 0.2.36 reflects the game and emulator of that period. Compatibility with current versions is unverified. Issues are closed and no further fixes are planned. [Maintenance record (Chinese)](docs/MAINTENANCE.md)

## Source & license

The repository provides source and design materials. The bundled executable, game asset packs, recognition templates, field captures and some runtime dependencies are unavailable here. With the documented environment, you can inspect the resource inventory and run the standalone treasure solver tests from the repository root. [Environment and reproduction guide (Chinese)](docs/SOURCE_DISTRIBUTION.md)

```powershell
python tools/check_source_assets.py
python -m unittest tests.test_treasure_solver tests.test_treasure_enumeration
```

Human and AI contributions that the author can license are covered by PolyForm Noncommercial 1.0.0. Commercial use requires separate permission. Retain the license and required notices. Third-party software, fonts, trademarks and game artwork visible in screenshots retain their respective rights.

[License](LICENSE) · [Scope](docs/legal/LICENSE_SCOPE.md) · [Third-party notices](docs/legal/THIRD_PARTY_NOTICES.md) · [Disclaimer](docs/legal/DISCLAIMER.md)

<!-- If the portfolio and contact links return, give them their own level-two heading here. -->
