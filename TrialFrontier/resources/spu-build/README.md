# SPU generation bundle

The installer reads six SPU regions from the user-provided EBOOT, lifts instructions with the included ps3recomp tools, applies generation recipes preserving existing fixes, and compiles LLVM IR locally.

`recipes.json` contains function boundaries, references to locally generated lines, ABI declarations and authored instrumentation/arithmetic-scope changes. It contains no original image bytes or generated IR. Numeric operands are read from the user's input. A structural check rejects incompatible layouts; this is not a fixed whole-ROM hash. Not all modified game versions are supported.

The compiled game expects these six images and ABI. Do not substitute a generic SPU build without preserving the recipes. Generated C/IR and object caches remain private local outputs.

For packaging, provide LLVM Clang 19 `clang-cl.exe` as `compiler/clang-cl.exe` and its resource headers as `compiler/include/`. These compiler binaries/headers are supplied in the full release ZIP, not tracked here. `crt/` contains the minimal declarations used for IR-only compilation; no Windows SDK or Visual Studio installation is required on the user's PC.

The bundled ps3recomp tools/headers retain their upstream MIT license. LLVM uses Apache-2.0 WITH LLVM-exception. No game/license rights are granted by these tools.
