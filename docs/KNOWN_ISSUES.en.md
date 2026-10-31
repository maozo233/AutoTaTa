<p><a href="KNOWN_ISSUES.md">简体中文</a> · <strong>English</strong> · <a href="../README.en.md">Back to overview</a></p>

# Known issues and validation limits in 0.2.36

**Functional version: 0.2.36 · Last functional maintenance / diagnostic replay: 2026-10-24 · End-of-maintenance declaration: 2026-10-28 · Documentation update: 2026-11-01. Maintenance has ended; no fixes or compatibility updates are promised.**

The implementation targets the game, MuMu emulator, and dependency environment used at that time. **Compatibility with current or future versions is not guaranteed.** “Latest” identifies the final historical package. Issues are disabled; this does not mean the listed problems are resolved.

This page separates unresolved cases, repaired historical defects, and pending live validation. The lineup image statistics cover 40 saved records from two machines, deduplicated into 25 source images. They are not a general accuracy benchmark and do not describe treasure coverage. Raw diagnostic images, personal paths, and device information are excluded from this showcase.

## Unresolved interaction and treasure issues

These reports were added on 2026-10-28. User feedback establishes a reported real-use problem, but does not replace a reproducible sequence. Existing code or historical tests do not prove that the interface works correctly.

| ID | Issue | Current status and impact |
| --- | --- | --- |
| LINEUP-UI-01 | Typing a keyword while manually adding or correcting a character does not effectively narrow the candidate list | **User-reported; unresolved.** Name filtering must not be described as reliably usable. A backend name-matching function exists, but native-window reproduction of input, candidate updates, and actual UI behavior remains incomplete; the root cause is unconfirmed |
| TREASURE-REC-01 | Treasure recognition still produces errors | **User-reported; unresolved.** No additional failure frames were provided in this update to isolate the errors. No repair or specific algorithmic cause is claimed. Manually check board bounds, cell states, treasure dimensions / quantities, and completion status |
| TREASURE-VAL-01 | No complete real high-level-stage validation to establish reliability | **Coverage gap; live acceptance incomplete.** Configuration presets for stages 1–24 are not stage-by-stage acceptance. Lower-stage checks or individual higher-stage images do not establish reliable continuous play in high-level stages |

### Lineup: text filtering when adding or correcting a character

The reported symptom is that typing does not narrow the choices. This is an **interaction issue**, separate from lineup-image recognition errors. Search cannot currently be promised as a quick, reliable way to find a character. Browsing the list is only a possible workaround; if the target cannot be found there either, the manual correction flow cannot be considered usable.

Also note the existing **recognize-and-deploy-on-import behavior**: there is no mandatory cell-by-cell review before attempting deployment. Cell editing is disabled during recognition / execution. Stop and wait for the operation to finish stopping before correcting cells; this does not resolve the filtering issue. Backend matching logic does not replace validation of real text input, Chinese input composition, and candidate-list refresh. None of these steps is identified as the confirmed root cause.

### Treasure: recognition and high-level-stage coverage

Treasure recognition still needs manual verification. An automatic-recognition button, a treasure-confirmation button, or displayed probabilities do not establish correct recognition or completed live validation. The report does not contain enough failure frames and steps to identify the specific recognition component at fault.

Test source includes saved images from stages 1, 2, and 10, along with scaling, sparse-board, and partly opened-board checks. These provide **partial offline coverage**. Complete continuous real-game acceptance covering recognition, updates after digging, manual correction, and stage transitions in high-level stages has not been established. Do not describe high-level stages as verified stable or all 24 stages as tested. Solver mathematics, limited interface checks, and application startup checks do not fill this gap. See [treasure image tests](../tests/test_treasure_vision.py) and [interaction-state tests](../tests/test_treasure_controls.py); the original images are excluded from this showcase.

These entries remain unresolved or unverified. Maintenance has ended; no repair schedule or future validation is promised.

## Unresolved: eight uncertain cells across four images

The replay located the boards in 21 complete images. Four of those images still contain uncertain cells. Positions below refer to a **5×5** board: rows run top to bottom, columns left to right, both starting at **1**. Sample letters are anonymous references within this page, not download links.

| Sample | Source size (width × height) | Cells with unconfirmed identities | Count |
| --- | --- | --- | --- |
| A · Yellow board | 274×257 px | Row 4, column 5 | 1 |
| B · Dark board | 335×272 px | Row 2, column 4 | 1 |
| C · Small yellow board / animated poses | 239×220 px | Row 2, column 2; row 3, column 4; row 4, column 4; row 5, columns 2 and 5 | 5 |
| D · Green board | 254×227 px | Row 3, column 4 | 1 |

These are **unconfirmed cells**, not eight confirmed wrong character assignments. They remain question marks because a trustworthy identity was not established. Candidate scores are not ground truth. Use the cell editor to verify a character or mark a cell empty, then check the full lineup. Retaining unknown cells does not establish successful complete deployment.

Previously confirmed identities did not change in this comparison. That does not rule out confident misidentifications on other images. Small images, animated poses, overlapping bodies, and neighboring badges still need manual review. Scenery-versus-character ambiguity is not considered fully solved.

## Screenshot scope and completeness

| Input | Current behavior / limitation | Practical handling |
| --- | --- | --- |
| A large capture containing chat, lists, unrelated UI, or multiple board-like regions | Automatic localization may choose the wrong candidate or fail. Arbitrary full-screen captures are not reliably supported | Keep the target board prominent; manually select the board if needed, then verify cells and identities |
| Only three or four rows of a 5×5 board are present | Four saved images have this problem. Version 0.2.36 rejects them before publishing deployment cells; manual selection does not bypass the check | Recapture all five rows and columns, **including empty rows and cells**. Do not stretch a partial board into five rows |
| Clipped characters, badges, or board edges; blur, compression, or occlusion | Unknown cells, missed characters, or localization failure may occur. Arbitrary scaling and occlusion are not covered by a reliability guarantee | Use a clear original image; preserve the complete board and character outlines; avoid excessive cropping and recompression |

The five-row requirement applies to 5×5 mode. Preserve the corresponding full 3×4 board in 3×4 mode. A complete but vertically compressed board differs from one with missing rows; historical complete compressed samples remain covered by regression checks. Manual selection helps localization, but cannot recover missing content or guarantee correct recognition.

## Deployment can still fail

One saved operation record still showed **6/15** after a drag. The expected seventh character had not appeared and the target cell was empty. Version 0.2.36 preserves the stop. There is no evidence that this input failure has been resolved, and the algorithm does not conceal it with blind repeated drags.

Two other historical false stops mixed old and new observations: an initial count of 6 followed by a confirmed count of 7, and an initial count of 15 followed by a cleared board with 0. The count comparison was repaired. Saved-frame replay returned **6, 7, and 0**, consistent with the detected positions. **This was offline replay; no game input was sent.**

Check the current screen and feedback when a drag has no effect or count, identity, or position cannot be confirmed. Recognizing the source image does not prove that the entire deployment completed reliably.

## Repaired historical defects

| Historical defect | Result in the 0.2.36 replay |
| --- | --- |
| Three missed character identities | Restored stalkerix, pearpair, and cheerlet; the eight cells listed above remain uncertain |
| Neighboring badges treated as extra occupied cells in two images | Both cells restored to empty; not a claim that all badge or scenery false positives are eliminated |
| Partial three- or four-row captures manually split into five rows | Explicit rejection with a request for the complete five rows, including empty rows |
| Initial count reused after scanning a changed board | Comparison now uses the count associated with the current board observation; real drag failures still stop |

Unknown cells in complete images decreased from 12 to 8. This also includes removal of false occupied cells, so the difference cannot be converted into general recognition accuracy. See the [historical validation summary (Chinese)](VALIDATION_SUMMARY.md).

## Validation and distribution limits

- **A complete real-game deployment with 0.2.36 remains pending retest.** The 197 historical lineup regression checks, window startup checks, and package verification do not replace live acceptance.
- The four feature screenshots show actual UI and isolated configuration states. They do not establish that fishing, treasure, rafting, and lineup deployment all work in the current game environment. Unverified scenarios are not presented as confirmed defects or successful repairs.
- The showcase omits diagnostic images, game recognition resources, and some third-party integration files. It cannot directly run the full suite or serve as a complete application distribution. See [source distribution boundaries (Chinese)](SOURCE_DISTRIBUTION.md).
- Maintenance has ended. These entries document limitations, not a backlog, repair schedule, or support promise. Read the [disclaimer (Chinese)](legal/DISCLAIMER.md) and [license scope (Chinese)](legal/LICENSE_SCOPE.md) before use.
