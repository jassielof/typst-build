const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const fangz = b.dependency(
        "fangz",
        .{
            .target = target,
            .optimize = optimize,
        },
    );

    const toml = b.dependency(
        "toml",
        .{
            .target = target,
            .optimize = optimize,
        },
    );

    const tempfile = b.dependency(
        "tempfile",
        .{
            .target = target,
            .optimize = optimize,
        },
    );

    const cli_mod = b.createModule(.{
        .root_source_file = b.path("src/cli/main.zig"),
        .target = target,
        .optimize = optimize,
        .imports = &.{
            .{
                .name = "fangz",
                .module = fangz.module("fangz"),
            },
            .{
                .name = "toml",
                .module = toml.module("toml"),
            },
            .{
                .name = "tempfile",
                .module = tempfile.module("tempfile"),
            },
        },
    });

    const exe = b.addExecutable(.{
        .name = "typm",
        .root_module = cli_mod,
    });

    b.installArtifact(exe);

    const cli_step = b.step("cli", "Run the CLI.");

    const run_cli = b.addRunArtifact(exe);
    cli_step.dependOn(&run_cli.step);

    run_cli.step.dependOn(b.getInstallStep());

    if (b.args) |args| {
        run_cli.addArgs(args);
    }

    const tests_step = b.step("tests", "Run the test suite");

    const unit_tests = b.addTest(.{
        .root_module = cli_mod,
    });

    const run_unit_tests = b.addRunArtifact(unit_tests);
    tests_step.dependOn(&run_unit_tests.step);
}
