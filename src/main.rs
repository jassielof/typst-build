use anyhow::{Context, Ok, Result, anyhow};
use clap::Parser;
use globset::{Glob, GlobSetBuilder};
use regex::Regex;
use serde::Deserialize;
use std::fs;
use std::{
    path::{Path, PathBuf},
    process::Command,
};
use walkdir::WalkDir;

#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[arg(value_name = "TOML_FILE")]
    toml_file: PathBuf,
    #[arg(long, value_name = "OUTPUT_DIR",default_value = "output", value_parser=["output","universe"])]
    output_dir: String,
}

#[derive(Debug, Deserialize)]
struct PackageConfig {
    name: String,
    version: String,
    exclude: Option<Vec<String>>,
    entrypoint: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TemplateConfig {
    path: Option<String>,
    entrypoint: Option<String>,
    thumbnail: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Config {
    package: PackageConfig,
    template: Option<TemplateConfig>,
}

fn validate_package_name(package_name: &str, toml_dir: &Path) -> Result<()> {
    let parent_dir_name = toml_dir
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| anyhow!("Could not determine parent directory name"))?;

    if package_name != parent_dir_name {
        return Err(anyhow!(
            "Package name '{}' does not match parent directory name '{}'",
            package_name,
            parent_dir_name
        ));
    }
    Ok(())
}

fn compile_template(
    toml_dir: &Path,
    package_name: &str,
    template_path: &str,
    template_entrypoint: &str,
) -> Result<()> {
    let template_full_path = Path::new(package_name)
        .join(template_path)
        .join(template_entrypoint);
    let output = Command::new("typst")
        .args(["compile", "--root", "."])
        .arg(&template_full_path)
        .current_dir(toml_dir.parent().unwrap())
        .output()
        .with_context(|| {
            format!(
                "Failed to compile template: {}",
                template_full_path.display()
            )
        })?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(anyhow!(
            "Template compilation failed\nStdout: {}\nStderr: {}",
            stdout,
            stderr
        ));
    }
    Ok(())
}

fn generate_thumbnail(
    toml_dir: &Path,
    package_name: &str,
    template_path: &str,
    template_entrypoint: &str,
    thumbnail_path: &str,
) -> Result<()> {
    let template_full_path = Path::new(package_name)
        .join(template_path)
        .join(template_entrypoint);
    let thumbnail_full_path = Path::new(package_name).join(thumbnail_path);

    let output = Command::new("typst")
        .args([
            "compile",
            "--root",
            ".",
            "--pages",
            "1",
            template_full_path.to_str().unwrap(),
            thumbnail_full_path.to_str().unwrap(),
        ])
        .current_dir(toml_dir.parent().unwrap())
        .output()
        .with_context(|| "Failed to generate thumbnail")?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(anyhow!(
            "Thumbnail generation failed\nStdout: {}\nStderr: {}",
            stdout,
            stderr
        ));
    }
    Ok(())
}
fn copy_files(
    source_dir: &Path,
    dest_dir: &Path,
    exclude_patterns: &[String],
    package_name: &str,
    package_version: &str,
    package_entrypoint: &str,
) -> Result<()> {
    // Create destination directory
    std::fs::create_dir_all(dest_dir)?;

    // Build glob set from exclude patterns
    let mut glob_builder = GlobSetBuilder::new();
    for pattern in exclude_patterns {
        let glob = Glob::new(pattern)?;
        glob_builder.add(glob);
    }
    let glob_set = glob_builder.build()?;

    // Precompute directory patterns (non-glob and directories)
    let directory_patterns: Vec<String> = exclude_patterns
        .iter()
        .filter(|p| !has_glob_metacharacters(p))
        .filter_map(|p| {
            let pattern_native = p.replace('/', &std::path::MAIN_SEPARATOR.to_string());
            let pattern_path = source_dir.join(&pattern_native);

            let is_dir_pattern = if p.ends_with('/') {
                true
            } else {
                pattern_path.is_dir()
            };

            is_dir_pattern.then(|| {
                pattern_native
                    .trim_end_matches(std::path::MAIN_SEPARATOR)
                    .to_string()
            })
        })
        .collect();

    // Process each file
    for entry in WalkDir::new(source_dir) {
        let entry = entry?;
        let src_path = entry.path();
        let rel_path = src_path.strip_prefix(source_dir)?;
        let rel_str = rel_path.to_str().ok_or_else(|| anyhow!("Invalid path"))?;

        // Check against glob patterns
        let rel_str_unix = rel_str.replace(std::path::MAIN_SEPARATOR, "/");
        if glob_set.is_match(&rel_str_unix) {
            continue;
        }

        // Check against directory patterns
        let excluded_by_dir = directory_patterns.iter().any(|pattern| {
            rel_str == pattern
                || rel_str.starts_with(&format!("{}{}", pattern, std::path::MAIN_SEPARATOR))
        });

        if excluded_by_dir {
            continue;
        }

        let dst_path = dest_dir.join(rel_path);

        if entry.file_type().is_dir() {
            std::fs::create_dir_all(&dst_path)?;
        } else {
            if src_path.ends_with("typst.toml") {
                // Remove lines starting with #:schema
                let content = std::fs::read_to_string(src_path)?;
                let filtered = content
                    .lines()
                    .filter(|line| !line.trim_start().starts_with("#:schema"))
                    .collect::<Vec<_>>()
                    .join("\n");
                std::fs::write(dst_path, filtered)?;
            } else if let Some(ext) = src_path.extension().and_then(|e| e.to_str()) {
                if ext == "typ" {
                    // Update import statements
                    let content = std::fs::read_to_string(src_path)?;
                    // ...existing code...
                    let entrypoint_name = Path::new(package_entrypoint)
                        .file_name()
                        .and_then(|n| n.to_str())
                        .ok_or_else(|| anyhow!("Invalid entrypoint name"))?;

                    // This regex matches: #import "<relpath><entrypoint>"<optional colon and specifier>
                    let re = Regex::new(&format!(
                        r#"#import\s+"((?:\.\./)+{})((?::\s*[^"]*)?)""#,
                        regex::escape(entrypoint_name)
                    ))?;

                    // Replacement: keep everything after the colon untouched
                    let package_import = format!("@preview/{}:{}", package_name, package_version);
                    let new_content = re.replace_all(&content, |caps: &regex::Captures| {
                        let specifier = caps.get(2).map(|m| m.as_str()).unwrap_or("");
                        format!("#import \"{}{}\"", package_import, specifier)
                    });
                    // ...existing code...
                    std::fs::write(dst_path, new_content.as_bytes())?;
                } else {
                    std::fs::copy(src_path, dst_path)?;
                }
            } else {
                std::fs::copy(src_path, dst_path)?;
            }
        }
    }

    Ok(())
}

fn has_glob_metacharacters(s: &str) -> bool {
    s.contains(|c| matches!(c, '*' | '?' | '[' | ']'))
}

fn main() -> Result<()> {
    let args = Cli::parse();

    // Resolve typst.toml path
    let toml_path = if args.toml_file.is_file() {
        args.toml_file
    } else if args.toml_file.is_dir() {
        let path = args.toml_file.join("typst.toml");
        if !path.exists() {
            return Err(anyhow!("No typst.toml found in directory"));
        }
        path
    } else {
        return Err(anyhow!("Path is neither file nor directory"));
    };

    let toml_dir = toml_path.parent().unwrap();

    // Parse TOML
    let config_content = fs::read_to_string(&toml_path)?;
    let config: Config = toml::from_str(&config_content)?;

    // Validate package name
    validate_package_name(&config.package.name, toml_dir)?;

    // Process template
    if let Some(template) = &config.template {
        if let (Some(path), Some(entrypoint)) = (&template.path, &template.entrypoint) {
            compile_template(toml_dir, &config.package.name, path, entrypoint)?;

            if let Some(thumbnail) = &template.thumbnail {
                generate_thumbnail(toml_dir, &config.package.name, path, entrypoint, thumbnail)?;
            }
        }
    }

    // Prepare output directory
    let output_base = Path::new(&args.output_dir);
    let output_dir = output_base
        .join(&config.package.name)
        .join(&config.package.version);

    // Copy files
    copy_files(
        toml_dir,
        &output_dir,
        &config.package.exclude.unwrap_or_default(),
        &config.package.name,
        &config.package.version,
        &config.package.entrypoint.as_deref().unwrap_or("main.typ"),
    )?;

    println!(
        "Package '{}' v{} built successfully to {}",
        config.package.name,
        config.package.version,
        output_dir.display()
    );

    Ok(())
}
