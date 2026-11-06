# NUP integration (experimental, v1.000.001)

**Base:** EglantinePS5 `main` ZIP supplied by the user, with `Eglantine` gitlink pinned at
`3140648a668aaebf87bae2dea17512fdca125ba0`. **Source of the NUP parser and loader:**
Lichii commit `31b901b93b992580d608fc2f4db9ddac1d755e43` (original NUP introduction,
GPL-3.0-or-later). **No Lichii `nx2` full-core upgrade is performed.**

## How this branch builds

`make deps` initializes the pinned core, fetches the named upstream NUP commit into
its *object database only* (`git fetch origin <sha>`), generates
`tools/eglantine-patches/0018-add-native-nup-support.patch` and applies it after the
17 original PS5 patches. The generated patch contains the four *actual* upstream NUP
source files and narrowly scoped registrations in the old core's CMake, core,
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
