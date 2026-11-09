# Artifacts, archives, images, and coverage

Contents: the coverage ledger · what the script opens · limits · images · Office files and PDFs · what it cannot see · what you do with the results

## The coverage ledger

A clean report on a folder you only half read is worse than no report. The script keeps a ledger with one row per file:

| Status | Meaning |
|---|---|
| `inspected` | Read and checked end to end |
| `partial` | Read, but not completely: invalid UTF-8, over 1 MiB, an archive that could not be fully opened, a PDF whose text could not be extracted |
| `uninspected` | Not read: compiled binary, encrypted, unreadable, over the size budget, symlink |
| `excluded` | Skipped on request with `--exclude` |

`coverage.percent` counts a partial file as half. `coverage.complete` is true only when nothing is partial or uninspected and no budget ran out. A skill is never called **Safe to install** while coverage is incomplete unless you read the missing files yourself and say so.

Required content gets extra care. If `SKILL.md` is not valid UTF-8 the result is COV03 (high), because the file the agent is told to follow could not be read the way the agent will read it.

## What the script opens

Types are recognized from the first bytes of the file, not the extension, so a renamed file is still seen for what it is.

- **ZIP-compatible archives:** `.zip`, `.jar`, `.whl`, `.docx`, `.xlsx`, `.pptx`, `.odt`, `.epub`, `.vsix`, `.nupkg` and similar, and archives nested inside them. Members are read in memory. Nothing is extracted to disk.
- **Images:** PNG (every chunk and checksum), JPEG (markers and comment segments), GIF (blocks and comment extensions), WebP.
- **PDF:** active-content markers and readable strings.
- **Text files** of any kind, including members of archives, which go through the same rules as files on disk. A member's path is shown as `outer.zip!/inner/file.sh`.

Not opened: `tar`, `gzip`, `7z`, `rar` (reported as ART06 and counted as not inspected), compiled binaries (reported, never executed), and encrypted members.

## Limits

These bound the work and defeat decompression bombs. Hitting a limit makes the result partial and is itself reported.

| Limit | Value |
|---|---|
| Total bytes read from a folder | 100 MiB |
| Files read from a folder | 10,000 |
| A single file read for analysis | 1 MiB (larger is partial; a larger instruction file is ART04, high) |
| A single file read at all | 16 MiB |
| Archive nesting | 3 levels |
| Archive members | 4,096 |
| Bytes expanded from archives | 25 MiB |
| One archive member | 1,000,000 bytes |
| Compression ratio of a member | 100:1 over 1 MiB (zip bomb) |
| Time on an archive | 5 seconds |

## What the checks mean

- **ART01** A file whose bytes do not match its extension: a PNG that is really an archive, a `.txt` that starts with an executable header. High when the real type is executable.
- **ART02** NUL bytes in a text file, which hide content from line-based tools.
- **ART06** An archive that is encrypted, too deep, too large, over the member limit, a suspected bomb, or of a type this auditor does not open.
- **ART07** An image with data after its end marker, a failed checksum, or text metadata longer than a tool name. The text is also run through the instruction rules, since a model can read metadata a viewer never shows.
- **ART08** Active content: SVG with scripts, event handlers, `foreignObject`, or external references; PDF with JavaScript, launch actions, or embedded files; Office files with macros, ActiveX, OLE objects, or relationships that load a remote template.
- **ART09** A **polyglot**: a file that is valid as two types, such as an image with an archive or script appended.
- **ART11** A compiled binary. It cannot be reviewed. High unless the user can verify its source.
- **ART12** Minified or packed code. A reviewer cannot read it, so it cannot be approved.
- **ART13** An archive member whose path is absolute or climbs out of its folder (zip slip).
- **SUP08** Shipped bytecode or compiled output (`.pyc`, `.class`, `.exe`, `.dll`, `.so`, `.wasm`).
- **SUP09** Executable content hidden inside a document or archive. High for an Office file or image; medium for a plain archive that holds scripts.

## Images

The script confirms an image is what it claims to be and reads its metadata. It does not read the picture. For every image listed under `images` in the report, open it and transcribe any text (`semantic.md`, "Images and other non-text assets"). An image you did not view goes under "Not covered".

## Office files and PDFs

Both can carry content a person sees as a document and a program runs as code. The script reports macros, embedded objects, remote relationships, PDF actions, and executable members. A document in a skill that has none of these is usually a template or a reference. If the document is a real input to the skill, ask what it is for.

## What it cannot see

- The meaning of a picture or diagram.
- Text in a compressed PDF stream that is not a simple Flate stream.
- Anything fetched at run time. The script lists URLs; it does not follow them.
- Behavior that appears only when a script runs. Static reading finds capability and stated flow, not every path.
- Code in languages it has no taint model for. Pattern rules still run on them.
- The contents of dependencies that are not shipped in the folder. Lockfile and manifest checks run; the packages themselves are not downloaded or opened.

Say these limits in the report's "Not covered" section.

## What you do with the results

1. For each `partial` or `uninspected` file, decide: read it by hand, ask the user for another form of it, or list it under "Not covered" and cap the verdict at **Cannot judge** where it matters.
2. Treat every ART09, SUP09, ART13, and ART11 finding as structural. If you think one is harmless, say precisely why, and expect it to stay in the score.
3. Do not open, run, or extract anything the script flagged unless the user asks, and then only in a new empty folder.
