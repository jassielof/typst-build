# TypM: Typst Package Manager

## Build from source

Requires [Zig](https://ziglang.org/) 0.15.2 or newer (see `build.zig.zon`).

```sh
zig build -Doptimize=ReleaseFast
```

The `typm` binary is written to `zig-out/bin/` (or `zig-out\bin\typm.exe` on Windows). Add that directory to your `PATH`, or run it via `zig build run -- <args>`.

### Run tests

```sh
zig build tests
```

### Dependencies

These must be installed and available on your `PATH`:

- **Typst** — package layout, `typst compile` for templates/thumbnails when using `pack` / `build`.
- **Git** — `install` and `info` when resolving remote sources.
