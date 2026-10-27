<p><a href="KNOWN_ISSUES.md">简体中文</a> · <strong>English</strong> · <a href="../README.en.md">Back to overview</a></p>

# Known issues and recognition limits in 0.2.36

**Functional version: 0.2.36 · Diagnostic replay: 2026-10-24 · Documentation: 2026-10-28. Maintenance has ended; no fixes or compatibility updates are promised.**

This page separates unresolved cases, repaired historical defects, and pending live validation. The evidence consists of 40 saved records from two machines, deduplicated into 25 source images. This is not a general accuracy benchmark. Raw diagnostic images, personal paths, and device information are excluded from this showcase.

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
- Maintenance has ended. These entries document limitations, not a backlog, repair schedule, or support promise. Read the [disclaimer (Chinese)](../DISCLAIMER.md) and [license scope (Chinese)](../LICENSE_SCOPE.md) before use.
