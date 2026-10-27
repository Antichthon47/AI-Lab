# Local AI coding workstation

Experimental workstation for evaluating local coding models. Inspected on
2026-10-26 at approximately 16:32 America/Chicago using read-only OS, NVIDIA,
systemd, Ollama CLI, and local API queries. This is an inventory, not an inference
benchmark; no generation requests were issued.

## Hardware and operating system

| Component | Observed configuration |
| --- | --- |
| CPU | AMD Ryzen 5 5600X, 6 cores / 12 threads, maximum reported clock 4.654 GHz |
| RAM | Nominal 32 GB; Linux reports 31 GiB, approximately 27 GiB available at inspection |
| Swap | 8 GiB, unused at inspection |
| GPU | NVIDIA GeForce RTX 3070 Ti, 8192 MiB VRAM |
| GPU snapshot | 391 MiB used, 52 °C, 83 W, 310 W reported power cap; display active |
| GPU consumers | Xorg, GNOME Shell, Firefox; desktop load can affect benchmark results |
| OS | Ubuntu 24.04.5 LTS (Noble Numbat), x86_64 |
| Kernel | 7.0.0-38-generic |
| NVIDIA driver | 595.99.02; `nvidia-smi` works |
| CUDA reported by driver | 13.2; this does not establish that a CUDA toolkit is installed |
| Utilities | Python 3.12.3, Git 2.43.0; curl available |

## Storage

Sizes below use the rounded binary units displayed by `df -hT` and `lsblk`.

| Device / filesystem | Capacity | State at inspection |
| --- | --- | --- |
| `/dev/sdb` | 232.9 GiB disk | Hosts Ubuntu |
| `/dev/sdb2`, ext4, `/` | 228 GiB filesystem | 25 GiB used, 192 GiB available; includes this workspace |
| `/dev/sdb1`, vfat | About 1 GiB | Mounted at `/boot/efi` |
| `/dev/nvme0n1` | 931.5 GiB disk | 931.5 GiB NTFS partition unmounted; free space not inspected |
| `/dev/sda` | 10.9 TiB disk | NTFS partition unmounted; free space not inspected |
| `/dev/sdc1`, exfat | 7.5 GiB filesystem | Ventoy USB mounted at `/media/binamra/Ventoy`, 1.7 GiB available |

Unmounted capacity is not counted as available workspace storage. No disks were
mounted or modified.

## Ollama configuration

- CLI and local `/api/version` both report **0.40.11**.
- System service is active/running, user and group `ollama`.
- Unit: `/etc/systemd/system/ollama.service`; executable:
  `/usr/local/bin/ollama serve`.
- Unit restart policy: `always`, delay 3 seconds.
- Listener observed at `127.0.0.1:11434`.
- The unit's reported environment contains PATH only; no explicit `OLLAMA_*`
  overrides were shown. Effective runtime defaults were not inferred from this.
- Service account home is `/usr/share/ollama`. The conventional model location
  `/usr/share/ollama/.ollama/models` could not be inspected due to permissions;
  actual storage path and disk usage remain unverified. No sudo inspection used.
- `ollama ps` was empty: no model loaded at inspection. GPU inference/offload
  remains to be verified during the first benchmark.

### Installed model

| Property | Observed value |
| --- | --- |
| Tag | `qwen3:8b` |
| Digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| Parameters / format | 8.2B / GGUF / Q4_K_M |
| API-reported size | 5,225,388,164 bytes |
| Advertised model context | 40,960 tokens; usable context and VRAM fit not yet measured |
| Capabilities | Completion, tools, thinking; thinking defaults to enabled |
| Sampling defaults | temperature 0.6, top_k 20, top_p 0.95, repeat_penalty 1 |
| Stop strings | `<\|im_start\|>` and `<\|im_end\|>` (literal strings without backslashes) |

## Benchmarking

See [benchmarks/README.md](benchmarks/README.md) for the experiment matrix,
measurement protocol, quality scoring, and future GPU-Unlock comparison gate.
No performance or coding-quality results exist yet.

## Change boundaries

This setup work adds documentation and benchmark fixtures only inside `~/AI-Lab`.
Do not install packages, change system settings, modify drivers, or enable
GPU-Unlock. Ask before making any changes outside `~/AI-Lab`, including model
downloads into Ollama's service-owned storage. GPU-Unlock is a future experiment;
its implementation, compatibility, and current presence were not audited here.
