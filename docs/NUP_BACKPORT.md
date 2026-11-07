# NUP integration (experimental, v1.000.006)

**Base:** EglantinePS5 `main` ZIP supplied by the user, with `Eglantine` gitlink pinned at
`3140648a668aaebf87bae2dea17512fdca125ba0`. **Source of the NUP parser and loader:**
Lichii commit `31b901b93b992580d608fc2f4db9ddac1d755e43` (original NUP introduction,
GPL-3.0-or-later). **No Lichii `nx2` full-core upgrade is performed.**

## How this branch builds

`make deps` initializes the pinned core, fetches the named upstream NUP commit into
its *object database only* (`git fetch origin <sha>`), generates
`tools/eglantine-patches/0018-add-native-nup-support.patch` and applies it after the
17 original PS5 patches. The generated patch contains the four upstream NUP source files (with a minimal
V1.000.003 dual-layout adaptation to `nup_container.cpp` only) and narrowly scoped registrations in the old core's CMake, core,
loader header and loader dispatch. The gitlink/HEAD remains unchanged.

The generated 0018 patch is deliberately not checked in because the normal GitHub
"Download ZIP" lacks the submodule; it is generated deterministically from two
immutable, full 40-character Git commit IDs. A build therefore requires GitHub
access to fetch the newer commit. The build aborts rather than silently updating
or guessing another core version if the pinned commit is missing.

NUP recognition is added for local `roms/`, NFS and USB/NTFS `games/` entries.
The game bridge reads the original NUP loader's title ID, game name, icon and
language metadata. Existing NSP/XCI and extracted-game paths remain unchanged.
Remote game downloads and external update/DLC discovery **remain NSP/XCI-only**;
NUP has different integrity and package semantics. Internal base+update overlay
uses the original NUP loader (its ability to mount NUP DLC is limited).

The main PS5 filesystem paths, active jail, firmware configuration, DNS, keys,
existing saves, homebrew identification `PPSA98515`, and the 17 PS5 patches
have not been intentionally modified.

## Build and validation

1. Create a separate test branch from the user's existing `main` (for example,
   `feature/native-nup-loader`). Do not copy the update ZIP onto the production
   branch until the new build has been independently verified.
2. Upload the root-relative files in the GitHub update ZIP. Do **not** place its
   contents under an extra top-level folder.
3. In GitHub Actions run **Release build** on the experimental branch. The action
   fetches the pinned NUP source, applies patch `0018`, then compiles the PS5 app.
4. Check the `Fetch dependencies` and build logs and inspect `0018` (it is
   generated in the CI workspace). A green compile validates linking only, **not**
   parsing of the user's actual `.nup` or gameplay on the real PS5.
5. After a successful build, back up any user saves, install the separate
   `EglantinePS5-v1.000.001.zip` and check that the existing NSP/XCI games still
   list and launch. Then put a **known-valid, legally obtained NUP** in
   `/data/eglantineps5/roms/`, reopen the launcher and inspect the game entry,
   icon/title and launch logs. Do not rename an NSP to NUP.
6. If the build fails, preserve the complete first error and the failing file/line;
   do not overwrite the known-good `v1.000.000` backup.

## Known unverified points

- **This patch has not been compiled with the PS5 toolchain here.** It requires
  an actual GitHub Actions build (and then a console test) before functionality
  can be confirmed.
- The pinned upstream NUP implementation decompresses a compressed member on
  a cache miss, with a cache cap of 512 MiB. This is *not* fixed-size chunk
  streaming; a member larger than the cap is still decompressed into a transient
  buffer. Large files may cause memory pressure on PS5; prolonged play and large
  NUP packages have not been validated.
- The uploaded 23.3-GB game archive was not provided for validation. Its four
  initial bytes matching `NUP\x01` do not prove its integrity or that the title
  will run.
- `make update` is intentionally disabled on this experimental branch to avoid
  accidentally rebasing the NUP backport and existing PS5 patches on a new core.

For a verified stable release, add a synthetic NUP integrity/malformed-header
suite, compile with CI and test on the real PS5 before merging the work.

## V1.000.003: validated NUP record layouts

Offline inspection of a user-supplied 64-KiB NUP prefix confirmed a valid SHA-256
TOC hash (from a separate full TOC check) and an aligned package/file record
layout different from the older pinned Lichii C++ structure. The first 635
file records fit the aligned layout; this is not proof that the whole NUP
container or game is valid. The Windows offline inspection is read-only.

At GitHub build time `tools/generate-nup-backport.py` transforms **only** the
upstream `nup_container.cpp` using `tools/nup_v1000003_layout.py`. The generated
0018 patch is still created from the immutable pinned git commits. It retains
the legacy layouts and parses the aligned package (metadata at +0x20/+0x28) and
file record (size +0x08, extent +0x10/+0x18, SHA-256 +0x20, codec +0x40).
The aligned metadata size is **u32**, codec/codec_flags are separate **u8** fields.
No unsupported codec, e.g. LZ4, is enabled. All file records are validated, and
ambiguous or inconsistent file layouts fail closed. The original ExeFS update
selection remains untouched; NUP's original `ErrorNUPNoBasePackage` behavior is
not bypassed. Existing 17 PS5 patches, NSP/XCI loading, Vulkan and PS5 App-ID
are unchanged. Only `sce_sys/param.json` has its version updated.

A local Python syntax test can validate the patch generator, but **no PS5 C++
compilation or hardware gameplay test has been performed** in this environment.
The Release build and real-console tests remain essential. On parser failure,
inspect the `NUP-DIAG` lines in stderr/eden logs for format/layout reasons.

## V1.000.004: narrow Switch 2 audio-device-manager backport

The PS5 V1.000.003 logs confirmed that `auddmg:u` was not registered immediately
before the guest SDK dereferenced a null interface. Original source of the
`auddmg:u` command-0 IPC object and its virtual-device commands: Lichii
`09b78bd2dfdd279cc81caed2a794ed85062725c9`,
`src/core/hle/service/audio/nx2_audio_device_manager.h`.

Patch `0019-switch2-auddmg-virtual-device-manager.patch` is a **separate** checked-in
patch applied after the generated NUP `0018`. It registers the dedicated
`auddmg:u` service, returns a genuine manager IPC object on command 0, and
implements upstream-defined virtual-device commands 0, 100, 300, 401 and 500.
The newer upstream sysmix code cannot be copied unchanged into the pinned core:
it depends on `Read32Acquire`, `StreamType::Sysmix`, `IsReady` and
`TryAppendOutputBlock`, which are not available in the pinned version.
Consequently stream commands 700 and 800 explicitly reply `ResultNotSupported`,
not false success; `audsmx:u` itself has **not** been ported. This may block
a later game-start stage, and is not represented as complete Switch 2 audio.

The NUP format/parser, original core gitlink, previous 17 patches, NSP/XCI,
PS5 app ID and Vulkan path are unchanged. Only a real GitHub Actions compile
and a real-PS5 run will verify whether the change works and where boot goes next.
Do not merge into `main` before existing games regressions have been tested.

## V1.000.005: Switch 2 sound mixer service and pinned-core compatibility adapter

Real-console V1.000.004 logs confirmed `auddmg:u` command 0 returns an IPC
object but `audsmx:u` remains absent in two starts; all four sessions still
ended in a guest `0xF001` panic at `sdk+0x1A5564`. This is **not** proof the
missing service is the sole cause. The `SFCI` domain-object warning is real,
but its attribution remains unverified.

Patch `0020-switch2-audsmx-sysmix-backport.patch` applies after the checked-in
0019 (which itself applies after generated NUP 0018). It adds `audsmx:u`
through the existing `audio.cpp` named-service registration, and shares
`Nx2SysmixStreams` between the existing auddmg virtual-device manager and
new `INx2AudioSoundMixerService`. Command 0 checks the copied process handle
and returns a real `INx2SysmixUserSession` IPC object. Its upstream commands
are 1/CreateStream, 2/EngageStreams, 3/DisengageStreams (not guessed 0-3).
CreateStream validates the mapped ring and returns an actual stream IPC object;
stream commands 0-8 and 12 follow upstream signatures; unimplemented 9-11
explicitly return `ResultNotSupported`. The auddmg virtual-device commands
700/800 now use the shared registry to attach/detach streams.

The native PCM16 ring is adapted from upstream commit
`09b78bd2dfdd279cc81caed2a794ed85062725c9` to pinned core
`3140648a668aaebf87bae2dea17512fdca125ba0`. The pinned sink has no
`StreamType::Sysmix`, `TryAppendOutputBlock`, or `IsReady`, and memory has no
`Read32Acquire`. Instead this adapter uses the existing `StreamType::Out`,
checks `GetQueueSize()` against a four-block bound before `AppendBuffer`,
uses guest `ReadBlock` plus a host acquire fence and `WriteExclusive32` for
the ring consumer. **These are not behaviorally identical to newer APIs.**
The older sink exposes no readiness/error API; backend failures cannot always
be detected. This requires testing on real hardware before declaring audio
correct or crash-free. No fake successful stream-open result is returned when
the host sink pointer is null or ring validation fails.

No forced NUP-as-NSP content-provider registration has been introduced: the
warning about `Game contents not registered` is emitted by NSP-only lookup
while the dedicated NUP loader already supplies merged RomFS via RomFSFactory.
The warning's causal relevance to `0xF001` remains unproven. NSP/XCI, prior
patches, main branch and PS5 App-ID were not modified by this update.

**Verification performed here:** 0020 patch syntax and full git-apply test
against a representative post-0019 fixture; ZIP CRC and changed-file audit.
**Not performed here:** full patch application to a real pinned submodule
checkout, PS5 C++ toolchain build, real hardware boot/audio test. Run GitHub
Actions Release on `feature/native-nup-loader` and inspect compile errors
before testing on the PS5.

## V1.000.006: Read-only SDK 0xF001 panic code-window capture

The controlled real-console V1.000.005 tests (TV and Handheld, with frame
 generation disabled) reproduced `SetTerminateResult 0xF001` and `svcBreak`
with identical relative offsets `sdk+0x1A5564` (PC) and `sdk+0xBC03C` (LR).
These offsets describe the observed SDK abort path, **not** a proven cause.
The existing backtrace already captures PC, LR, SP and X0-X30, and the
`svcBreak` handler already logs the four-byte `0xF001` buffer. Therefore this
version does **not** duplicate the register dump or guess SDK assertion strings.

Patch `0021-switch2-sdk-f001-code-window-diagnostics.patch` is applied after
`0020` and changes **only**
`src/core/hle/kernel/svc/svc_exception.cpp` in the pinned Lichii submodule.
The diagnostic triggers only for a non-notification `BreakReason::Panic` whose
four-byte guest debug buffer can be read and equals `0xF001`. The handler
captures the live ARM CPU context, and safely checks guest virtual-memory
mapping and each read. It logs two windows of **raw 32-bit little-endian ARM64
instruction words** with guest virtual addresses (no binary dumping, no
disassembly, no mutation or code patches):

- `CALLER_LR`: LR minus `0x2C` through LR plus `0x24`, inclusive (21 words).
  If LR still corresponds to `sdk+0xBC03C`, this is `sdk+0xBC010..0xBC060`.
- `PANIC_PC`: PC minus `0x14` through PC plus `0x1C`, inclusive (13 words).
  If PC still corresponds to `sdk+0x1A5564`, this is `sdk+0x1A5550..0x1A5580`.

Filter the new `eden_log.txt` for `SDK_PANIC_DIAG`. The output includes each
window address and raw opcode. A future offline ARM64 disassembly of these
words can confirm local branches and control flow; it **cannot on its own**
identify a failed IPC service or SDK source symbol without more evidence.
An `unmapped`/`unreadable` diagnostic line is an intentional guarded outcome.
If no `0xF001` occurs, there will be no `SDK_PANIC_DIAG` lines.

No changes to game or SDK code, NSP/XCI/NUP loading, PS5 App-ID, audio services,
Vulkan, JIT, core gitlink or older patches. The actual root cause of `0xF001`
is still unknown; frame generation is not required for the panic to occur.

**Validation completed:** patch applies and reverses on a pinned-commit source
fixture (the prior patches do not touch this file); isolated C++20 smoke test
of the capture logic and its failure guards; delta audit and ZIP CRC checks.
**Not yet validated:** complete PS5 toolchain build / real-console run.


## V1.000.009: Switch 2 WaitIfEqual64 kernel backport and diagnostic

Based on the pinned Lichii `3140648a668aaebf87bae2dea17512fdca125ba0`,
patch `0024-switch2-wait-if-equal64-arb-diag.patch` adds the address arbiter
`WaitIfEqual64` mode (arbitration type 3) from the functioning Windows Eglantine
`216d3e294367abd4742d7ebd736ef25a8db6f365` kernel. The pinned PS5 core
otherwise rejects type 3 with `ResultInvalidEnumValue` (`0xF001`). Whether that
specific failure causes Zelda's SDK panic has **not been established**.

The patch adjusts the type enum, the 8-byte address alignment, 64-bit guest
memory comparison, the existing scheduler-lock-and-sleep wait path, the
`KProcess` parameter, SVC declarations, the 64-bit dispatch wrapper's X2
argument, and `tools/svc_generator.py` so regenerating the wrapper preserves
64-bit argument semantics. The legacy 32-bit modes retain 32-bit comparisons;
no new PS5-specific wait loop or custom thread/timer ownership is introduced.

Diagnostic messages for the first 32 `WaitIfEqual64` SVC calls start with
`[ARB-DIAG]` and include guest address, full 64-bit value, timeout, and (after
the wait returns) kernel result. Unsupported arbitration types are logged as
errors. An additional `[SVC-F001]` diagnostic records the SVC identifier
and original input registers whenever a 64-bit Switch 2 SVC leaves X0 equal to
`0xF001`; it can also reveal a different SVC returning that value. This is
an X0 observation, not automatically proof of a kernel Result return for every
SVC. **A logged call by itself does not prove the previous crash originated
there.** A waiting thread may not produce a corresponding return line until
signalled. The separate Zelda NSP loader failure is not modified in this update.

Only patch 0024, this documentation and `sce_sys/param.json` are changed in the
GitHub update ZIP. Existing patches 0001-0023, the pinned submodule commit,
PS5 application ID, and PS5/launcher/renderer settings are unchanged.

**Validation limitation:** The new patch was applied and reversed against
fixtures assembled from source excerpts of the pinned commit and checked for
structural consistency. The complete original Eglantine submodule and native
PS5 toolchain are not included in the source backup, so application against a
real checkout, C++ compilation, runtime SVC behavior, and Zelda boot must be
checked with the GitHub Actions release build and on the console. If the build
reports a patch conflict, do not force application or alter the pinned core.

Test only the original NUP initially. Inspect `eden_log.txt` for `[ARB-DIAG]`, `[SVC-F001]`,
`SetTerminateResult`, `Userspace PANIC`, `PresentClientBuffer` and the first
frame. Absence of `[ARB-DIAG]` does not alone prove Zelda never calls type 3;
confirm the configured log filter and ensure v1.000.009 is running.
