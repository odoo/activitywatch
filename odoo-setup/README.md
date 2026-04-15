# ActivityWatch Odoo Package Build

Build script for Odoo version of ActivityWatch packages for Linux (Debian/Ubuntu) and Windows.

## Requirements

- Docker
- `realpath` (coreutils)
- Sufficient disk space (~2GB for Docker images + build artifacts)

## Usage

```bash
./buildpackage.sh <distro> [package_name]
```

### Arguments

| Argument | Description | Default |
|---|---|---|
| `distro` | Target platform (`noble`, `jammy`, `windows`) | `noble` |
| `package_name` | Output package name | `activitywatch-odoo-<distro>` |

### Examples

```bash
# Build Ubuntu 24.04 package
./buildpackage.sh noble

# Build Ubuntu 22.04 package
./buildpackage.sh jammy

# Build Windows installer
./buildpackage.sh windows

# Custom package name
./buildpackage.sh jammy activitywatch-custom
```

## Outputs

After a successful build, artifacts are available in `odoo-setup/dist/`:

| Platform | Output |
|---|---|
| Linux | `activitywatch-odoo-<distro>.deb` |
| Windows | `activitywatch-odoo-YYYY-MM-DD-windows-x86_64-setup.exe` + `.zip` |

## Troubleshooting

### Docker permission errors

Ensure your user is in the `docker` group:

```bash
sudo usermod -aG docker $USER
```
