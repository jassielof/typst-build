const std = @import("std");
const builtin = @import("builtin");
const fangz = @import("fangz");
const toml = @import("toml");
const tempfile = @import("tempfile");
const GitSource = @import("../GitSource.zig").GitSource;

const PackageFile = struct {
    package: ?PackageSection = null,
};

const PackageSection = struct {
    name: ?[]const u8 = null,
    version: ?[]const u8 = null,
    description: ?[]const u8 = null,
    authors: ?[]const []const u8 = null,
    license: ?[]const u8 = null,
    homepage: ?[]const u8 = null,
    repository: ?[]const u8 = null,
};

pub fn register(root: *fangz.Command) !void {
    const cmd = try root.addSubcommand(.{
        .name = "info",
        .description = "information",
    });

    cmd.setHelpOnEmptyArgs(true);
    cmd.setHooks(.{
        .run = run,
    });

    try cmd.addPositional(.{
        .name = "package",
        .description = "Name of the package to display information about",
        .required = true,
    });
}

fn run(ctx: *fangz.ParseContext) !void {
    const allocator = ctx.allocator;
    const package_name = ctx.positional(0) orelse return error.MissingRequiredPositional;

    if (try tryPrintInstalledPackageInfo(allocator, package_name)) {
        return;
    }

    var source = parseGitSource(allocator, package_name) catch {
        failWithDetail("Invalid Git source URL or alias:", package_name);
    };
    defer source.deinit(allocator);

    try std.fs.cwd().makePath(".typm-tmp");
    var temp_dir = try tempfile.builder().prefix("typm-info-git-").tempDirIn(allocator, ".typm-tmp");
    defer temp_dir.deinit();

    var stdout_buffer: [4096]u8 = undefined;
    var stdout_writer = std.fs.File.stdout().writer(&stdout_buffer);
    try stdout_writer.interface.print("Cloning {s}...\n", .{source.repo_url_for_clone});
    try stdout_writer.interface.flush();

    try cloneRepository(allocator, &source, temp_dir.path());

    const search_dir = if (source.path_in_repo.len == 0)
        try allocator.dupe(u8, temp_dir.path())
    else
        try std.fs.path.join(allocator, &.{ temp_dir.path(), source.path_in_repo });
    defer allocator.free(search_dir);

    var toml_paths = std.ArrayList([]u8).empty;
    defer {
        for (toml_paths.items) |path| allocator.free(path);
        toml_paths.deinit(allocator);
    }

    const direct_toml = try std.fs.path.join(allocator, &.{ search_dir, "typst.toml" });
    defer allocator.free(direct_toml);

    if (fileExists(direct_toml)) {
        try toml_paths.append(allocator, try allocator.dupe(u8, direct_toml));
    } else {
        try collectTypstTomlFiles(allocator, search_dir, &toml_paths);
    }

    if (toml_paths.items.len == 0) {
        failWithDetail("No typst.toml found in the cloned repository:", search_dir);
    }

    if (toml_paths.items.len > 1) {
        try stdout_writer.interface.print("\nMultiple packages found in this monorepo:\n\n", .{});
        try stdout_writer.interface.flush();
    }

    for (toml_paths.items, 0..) |toml_path, index| {
        const rel_dir = try relativeParentDir(allocator, temp_dir.path(), toml_path);
        defer allocator.free(rel_dir);

        try printPackageInfoFromToml(allocator, toml_path, if (toml_paths.items.len > 1) rel_dir else null);

        if (toml_paths.items.len > 1 and index + 1 < toml_paths.items.len) {
            try stdout_writer.interface.print("\n", .{});
            try stdout_writer.interface.flush();
        }
    }
}

fn tryPrintInstalledPackageInfo(allocator: std.mem.Allocator, package_name: []const u8) !bool {
    const data_dir = try typstDataDir(allocator);
    defer allocator.free(data_dir);

    const package_dir = try std.fs.path.join(allocator, &.{ data_dir, "packages", package_name });
    defer allocator.free(package_dir);

    if (!dirExists(package_dir)) return false;

    const toml_path = try std.fs.path.join(allocator, &.{ package_dir, "typst.toml" });
    defer allocator.free(toml_path);

    if (!fileExists(toml_path)) {
        failWithDetail("No typst.toml found in the package directory:", package_dir);
    }

    try printPackageInfoFromToml(allocator, toml_path, null);
    return true;
}

fn printPackageInfoFromToml(allocator: std.mem.Allocator, toml_path: []const u8, monorepo_path: ?[]const u8) !void {
    const content = try std.fs.cwd().readFileAlloc(allocator, toml_path, 1024 * 1024);
    defer allocator.free(content);

    const parsed = try toml.parse(PackageFile, allocator, content);
    const package = parsed.package orelse PackageSection{};

    const name = package.name orelse "<unknown>";
    const version = package.version orelse "<unknown>";
    const description = package.description;
    const authors = try joinAuthors(allocator, package.authors);
    defer allocator.free(authors);

    var stdout_buffer: [4096]u8 = undefined;
    var stdout_writer = std.fs.File.stdout().writer(&stdout_buffer);

    if (monorepo_path) |path| {
        try stdout_writer.interface.print("Monorepo Path: {s}\n", .{if (path.len == 0) "." else path});
    }

    try stdout_writer.interface.print("Package: {s}\n", .{name});
    try stdout_writer.interface.print("Version: {s}\n", .{version});
    if (description) |value| {
        if (value.len > 0) try stdout_writer.interface.print("Description: {s}\n", .{value});
    }
    if (authors.len > 0) try stdout_writer.interface.print("Authors: {s}\n", .{authors});
    try stdout_writer.interface.print("License: {s}\n", .{package.license orelse "<unknown>"});
    if (package.homepage) |value| {
        if (value.len > 0) try stdout_writer.interface.print("Homepage: {s}\n", .{value});
    }
    if (package.repository) |value| {
        if (value.len > 0) try stdout_writer.interface.print("Repository: {s}\n", .{value});
    }
    try stdout_writer.interface.flush();
}

fn joinAuthors(allocator: std.mem.Allocator, authors: ?[]const []const u8) ![]u8 {
    const items = authors orelse return try allocator.dupe(u8, "");
    if (items.len == 0) return try allocator.dupe(u8, "");

    var builder = std.ArrayList(u8).empty;
    defer builder.deinit(allocator);

    for (items, 0..) |author, index| {
        if (index != 0) try builder.appendSlice(allocator, ", ");
        try builder.appendSlice(allocator, author);
    }

    return builder.toOwnedSlice(allocator);
}

fn cloneRepository(allocator: std.mem.Allocator, source: *const GitSource, clone_dir: []const u8) !void {
    var argv = std.ArrayList([]const u8).empty;
    defer argv.deinit(allocator);

    try argv.appendSlice(allocator, &.{ "git", "clone", "--depth", "1" });
    if (source.git_ref) |git_ref| {
        try argv.appendSlice(allocator, &.{ "--branch", git_ref });
    }
    try argv.appendSlice(allocator, &.{ source.repo_url_for_clone, clone_dir });

    const result = try std.process.Child.run(.{
        .allocator = allocator,
        .argv = argv.items,
    });
    defer {
        allocator.free(result.stdout);
        allocator.free(result.stderr);
    }

    if (result.term.Exited != 0) {
        if (result.stderr.len > 0) {
            printRawError(result.stderr) catch {};
        } else {
            printError("Failed to clone repository.", null) catch {};
        }
        std.process.exit(1);
    }
}

fn parseGitSource(allocator: std.mem.Allocator, input: []const u8) !GitSource {
    if (try tryParseAliasForm(allocator, input)) |source| return source;
    return parseGitUrl(allocator, input);
}

fn tryParseAliasForm(allocator: std.mem.Allocator, input: []const u8) !?GitSource {
    var parts = std.mem.splitScalar(u8, input, '/');
    const alias = parts.next() orelse return null;
    const user = parts.next() orelse return null;
    const repo = parts.next() orelse return null;

    const host = blk: {
        if (std.ascii.eqlIgnoreCase(alias, "gh") or std.ascii.eqlIgnoreCase(alias, "github")) break :blk "github.com";
        if (std.ascii.eqlIgnoreCase(alias, "gl") or std.ascii.eqlIgnoreCase(alias, "gitlab")) break :blk "gitlab.com";
        if (std.ascii.eqlIgnoreCase(alias, "bb") or std.ascii.eqlIgnoreCase(alias, "bitbucket")) break :blk "bitbucket.org";
        return null;
    };

    if (user.len == 0 or repo.len == 0) return null;

    var remainder = std.ArrayList([]const u8).empty;
    defer remainder.deinit(allocator);
    while (parts.next()) |segment| {
        try remainder.append(allocator, segment);
    }

    return GitSource{
        .repo_url_for_clone = try std.fmt.allocPrint(allocator, "https://{s}/{s}/{s}.git", .{ host, user, repo }),
        .git_ref = null,
        .path_in_repo = try joinPathSegments(allocator, remainder.items),
        .provider_host = try allocator.dupe(u8, host),
        .user_or_org = try allocator.dupe(u8, user),
    };
}

fn parseGitUrl(allocator: std.mem.Allocator, input: []const u8) !GitSource {
    const scheme_index = std.mem.indexOf(u8, input, "://") orelse return error.InvalidGitSource;
    const after_scheme = input[scheme_index + 3 ..];
    const host_end = std.mem.indexOfScalar(u8, after_scheme, '/') orelse return error.InvalidGitSource;

    var host = after_scheme[0..host_end];
    if (std.mem.startsWith(u8, host, "www.")) host = host[4..];

    var path = after_scheme[host_end + 1 ..];
    if (std.mem.indexOfAny(u8, path, "?#")) |idx| path = path[0..idx];

    var segments = std.ArrayList([]const u8).empty;
    defer segments.deinit(allocator);

    var it = std.mem.splitScalar(u8, path, '/');
    while (it.next()) |segment| {
        if (segment.len == 0) continue;
        try segments.append(allocator, segment);
    }

    if (segments.items.len < 2) return error.InvalidGitSource;

    if (std.mem.eql(u8, host, "github.com")) {
        return parseGithubUrl(allocator, host, segments.items);
    }
    if (std.mem.eql(u8, host, "gitlab.com")) {
        return parseGitlabUrl(allocator, host, segments.items);
    }
    if (std.mem.eql(u8, host, "bitbucket.org")) {
        return parseBitbucketUrl(allocator, host, segments.items);
    }

    return error.UnsupportedGitProvider;
}

fn parseGithubUrl(allocator: std.mem.Allocator, host: []const u8, segments: []const []const u8) !GitSource {
    const user = segments[0];
    const repo = trimGitSuffix(segments[1]);
    var git_ref: ?[]u8 = null;
    var path_parts: []const []const u8 = &.{};

    if (segments.len > 3 and (std.mem.eql(u8, segments[2], "tree") or std.mem.eql(u8, segments[2], "blob"))) {
        git_ref = try allocator.dupe(u8, segments[3]);
        path_parts = segments[4..];
    } else if (segments.len > 2) {
        path_parts = segments[2..];
    }

    return GitSource{
        .repo_url_for_clone = try std.fmt.allocPrint(allocator, "https://{s}/{s}/{s}.git", .{ host, user, repo }),
        .git_ref = git_ref,
        .path_in_repo = try joinPathSegments(allocator, path_parts),
        .provider_host = try allocator.dupe(u8, host),
        .user_or_org = try allocator.dupe(u8, user),
    };
}

fn parseGitlabUrl(allocator: std.mem.Allocator, host: []const u8, segments: []const []const u8) !GitSource {
    const user = segments[0];
    const repo = trimGitSuffix(segments[1]);
    var git_ref: ?[]u8 = null;
    var path_parts: []const []const u8 = &.{};

    if (segments.len > 4 and std.mem.eql(u8, segments[2], "-") and (std.mem.eql(u8, segments[3], "tree") or std.mem.eql(u8, segments[3], "blob"))) {
        git_ref = try allocator.dupe(u8, segments[4]);
        path_parts = segments[5..];
    } else if (segments.len > 2) {
        path_parts = segments[2..];
    }

    return GitSource{
        .repo_url_for_clone = try std.fmt.allocPrint(allocator, "https://{s}/{s}/{s}.git", .{ host, user, repo }),
        .git_ref = git_ref,
        .path_in_repo = try joinPathSegments(allocator, path_parts),
        .provider_host = try allocator.dupe(u8, host),
        .user_or_org = try allocator.dupe(u8, user),
    };
}

fn parseBitbucketUrl(allocator: std.mem.Allocator, host: []const u8, segments: []const []const u8) !GitSource {
    const user = segments[0];
    const repo = trimGitSuffix(segments[1]);
    const path_parts = if (segments.len > 2) segments[2..] else &.{};

    return GitSource{
        .repo_url_for_clone = try std.fmt.allocPrint(allocator, "https://{s}/{s}/{s}.git", .{ host, user, repo }),
        .git_ref = null,
        .path_in_repo = try joinPathSegments(allocator, path_parts),
        .provider_host = try allocator.dupe(u8, host),
        .user_or_org = try allocator.dupe(u8, user),
    };
}

fn joinPathSegments(allocator: std.mem.Allocator, segments: []const []const u8) ![]u8 {
    if (segments.len == 0) return try allocator.dupe(u8, "");

    var builder = std.ArrayList(u8).empty;
    defer builder.deinit(allocator);

    for (segments, 0..) |segment, index| {
        if (index != 0) try builder.append(allocator, std.fs.path.sep);
        try builder.appendSlice(allocator, segment);
    }

    return builder.toOwnedSlice(allocator);
}

fn trimGitSuffix(segment: []const u8) []const u8 {
    if (std.mem.endsWith(u8, segment, ".git")) return segment[0 .. segment.len - 4];
    return segment;
}

fn typstDataDir(allocator: std.mem.Allocator) ![]u8 {
    return switch (builtin.os.tag) {
        .windows => blk: {
            const base = getEnvOrHomeFallback(allocator, &.{"APPDATA"}, &.{ "AppData", "Roaming" }) catch |err| break :blk err;
            defer allocator.free(base);
            break :blk std.fs.path.join(allocator, &.{ base, "typst" });
        },
        .macos => blk: {
            const base = try getHomeWithSuffix(allocator, &.{ "Library", "Application Support" });
            defer allocator.free(base);
            break :blk std.fs.path.join(allocator, &.{ base, "typst" });
        },
        else => blk: {
            const base = getEnvOrHomeFallback(allocator, &.{"XDG_DATA_HOME"}, &.{ ".local", "share" }) catch |err| break :blk err;
            defer allocator.free(base);
            break :blk std.fs.path.join(allocator, &.{ base, "typst" });
        },
    };
}

test typstDataDir {
    const dir = try typstDataDir(std.testing.allocator);
    defer std.testing.allocator.free(dir);
    std.debug.print("Data dirs: {s}\n", .{dir});
}

fn getEnvOrHomeFallback(allocator: std.mem.Allocator, env_names: []const []const u8, home_suffix: []const []const u8) ![]u8 {
    for (env_names) |name| {
        const value = std.process.getEnvVarOwned(allocator, name) catch |err| switch (err) {
            error.EnvironmentVariableNotFound => continue,
            else => return err,
        };
        return value;
    }

    return getHomeWithSuffix(allocator, home_suffix);
}

fn getHomeWithSuffix(allocator: std.mem.Allocator, suffix: []const []const u8) ![]u8 {
    const home = try getHomeDir(allocator);
    defer allocator.free(home);

    var parts = std.ArrayList([]const u8).empty;
    defer parts.deinit(allocator);
    try parts.append(allocator, home);
    try parts.appendSlice(allocator, suffix);
    return std.fs.path.join(allocator, parts.items);
}

fn getHomeDir(allocator: std.mem.Allocator) ![]u8 {
    if (builtin.os.tag == .windows) {
        if (std.process.getEnvVarOwned(allocator, "USERPROFILE")) |userprofile| {
            return userprofile;
        } else |err| switch (err) {
            error.EnvironmentVariableNotFound => {},
            else => return err,
        }

        if (std.process.getEnvVarOwned(allocator, "HOME")) |home| {
            return home;
        } else |err| switch (err) {
            error.EnvironmentVariableNotFound => return error.HomeDirectoryNotFound,
            else => return err,
        }
    }

    const home = std.process.getEnvVarOwned(allocator, "HOME") catch |err| switch (err) {
        error.EnvironmentVariableNotFound => return error.HomeDirectoryNotFound,
        else => return err,
    };
    return home;
}

fn collectTypstTomlFiles(allocator: std.mem.Allocator, dir_path: []const u8, out: *std.ArrayList([]u8)) !void {
    var dir = try std.fs.cwd().openDir(dir_path, .{ .iterate = true });
    defer dir.close();

    var it = dir.iterate();
    while (try it.next()) |entry| {
        const child_path = try std.fs.path.join(allocator, &.{ dir_path, entry.name });
        errdefer allocator.free(child_path);

        switch (entry.kind) {
            .file => {
                if (std.mem.eql(u8, entry.name, "typst.toml")) {
                    try out.append(allocator, child_path);
                    continue;
                }
            },
            .directory => {
                if (std.mem.eql(u8, entry.name, ".git")) {
                    allocator.free(child_path);
                    continue;
                }
                try collectTypstTomlFiles(allocator, child_path, out);
                allocator.free(child_path);
                continue;
            },
            else => {},
        }

        allocator.free(child_path);
    }
}

fn relativeParentDir(allocator: std.mem.Allocator, root: []const u8, file_path: []const u8) ![]u8 {
    const parent = std.fs.path.dirname(file_path) orelse return try allocator.dupe(u8, ".");
    return std.fs.path.relative(allocator, root, parent);
}

fn fileExists(path: []const u8) bool {
    const file = std.fs.cwd().openFile(path, .{}) catch return false;
    file.close();
    return true;
}

fn dirExists(path: []const u8) bool {
    var dir = std.fs.cwd().openDir(path, .{}) catch return false;
    dir.close();
    return true;
}

fn failWithDetail(message: []const u8, detail: []const u8) noreturn {
    printError(message, detail) catch {};
    std.process.exit(1);
}

fn printError(message: []const u8, detail: ?[]const u8) !void {
    var stderr_buffer: [4096]u8 = undefined;
    var stderr_writer = std.fs.File.stderr().writer(&stderr_buffer);
    if (detail) |value| {
        try stderr_writer.interface.print("{s} {s}\n", .{ message, value });
    } else {
        try stderr_writer.interface.print("{s}\n", .{message});
    }
    try stderr_writer.interface.flush();
}

fn printRawError(message: []const u8) !void {
    var stderr_buffer: [4096]u8 = undefined;
    var stderr_writer = std.fs.File.stderr().writer(&stderr_buffer);
    try stderr_writer.interface.print("{s}", .{message});
    if (!std.mem.endsWith(u8, message, "\n")) {
        try stderr_writer.interface.print("\n", .{});
    }
    try stderr_writer.interface.flush();
}

test "parse alias git source" {
    const testing = std.testing;
    const expected_path = if (std.fs.path.sep == '\\') "templates\\report" else "templates/report";

    var source = try parseGitSource(testing.allocator, "gh/example/demo/templates/report");
    defer source.deinit(testing.allocator);

    try testing.expectEqualStrings("https://github.com/example/demo.git", source.repo_url_for_clone);
    try testing.expect(source.git_ref == null);
    try testing.expectEqualStrings(expected_path, source.path_in_repo);
    try testing.expectEqualStrings("github.com", source.provider_host);
    try testing.expectEqualStrings("example", source.user_or_org);
}

test "parse github tree url" {
    const testing = std.testing;
    const expected_path = if (std.fs.path.sep == '\\') "packages\\report" else "packages/report";

    var source = try parseGitSource(testing.allocator, "https://github.com/example/demo/tree/main/packages/report");
    defer source.deinit(testing.allocator);

    try testing.expectEqualStrings("https://github.com/example/demo.git", source.repo_url_for_clone);
    try testing.expectEqualStrings("main", source.git_ref.?);
    try testing.expectEqualStrings(expected_path, source.path_in_repo);
}
