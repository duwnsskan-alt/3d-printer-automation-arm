# Cloud Infrastructure for NVIDIA Isaac Lab Simulation

**Project:** 3d-printer-automation-arm  
**Date:** 2026-03-06  
**Purpose:** Run Isaac Lab RL training & synthetic data generation on cloud GPU instances

---

## 1. Recommended Cloud GPU Instances

### AWS EC2

| Instance | GPU | VRAM | Best For | On-Demand $/hr (approx) |
|----------|-----|------|----------|------------------------|
| **g5.xlarge** | 1× A10G | 24 GB | Dev/test, small RL runs | ~$1.01 |
| **g5.2xlarge** | 1× A10G | 24 GB | RL training + more CPU/RAM | ~$1.21 |
| **g5.12xlarge** | 4× A10G | 96 GB | Multi-env parallel training | ~$5.67 |
| **g6.xlarge** | 1× L4 | 24 GB | Inference, light sim | ~$0.80 |
| **p4d.24xlarge** | 8× A100 (40GB) | 320 GB | Large-scale domain rand / massive parallel envs | ~$32.77 |
| **p5.48xlarge** | 8× H100 | 640 GB | Overkill for most sim; future-proof | ~$98.32 |

**Recommendation for this project:**
- **Development & iteration:** `g5.xlarge` or `g5.2xlarge` (Spot @ ~60% discount)
- **Production training runs:** `g5.12xlarge` (4× A10G) — sweet spot for Isaac Lab parallel envs
- **Large-scale synthetic data generation:** `p4d.24xlarge` if generating millions of frames with heavy domain randomization

### NVIDIA Cloud Options

| Service | Description | When to Use |
|---------|-------------|-------------|
| **NGC Catalog** | Pre-built Isaac Sim/Lab containers | Always — base your Docker images on these |
| **Base Command Platform** | Multi-node GPU cluster orchestration | Enterprise-scale training (100s of GPUs) |
| **DGX Cloud** | Managed DGX infrastructure on AWS/Azure/GCP | If budget allows; turnkey Isaac Sim support |
| **Omniverse Cloud** | Streaming Omniverse apps | Interactive review of sim scenes (not training) |

For this project's scale (single robotic arm), **NGC containers on AWS Spot g5 instances** is the practical choice. Base Command / DGX Cloud are overkill unless scaling to fleet-level training.

---

## 2. Containerization with NGC & Docker

### Base Container

Isaac Lab runs on top of Isaac Sim. NVIDIA provides official containers:

```dockerfile
# Dockerfile for Isaac Lab headless training
FROM nvcr.io/nvidia/isaac-sim:4.5.0  
# (or latest; check NGC catalog for current tag)

# Install Isaac Lab
RUN git clone https://github.com/isaac-sim/IsaacLab.git /opt/isaaclab \
    && cd /opt/isaaclab \
    && ./isaaclab.sh --install

# Copy project-specific assets and configs
COPY ./envs/printer_arm_env.py /opt/isaaclab/source/extensions/
COPY ./configs/ /opt/isaaclab/configs/
COPY ./assets/arm_usd/ /opt/isaaclab/assets/

# Set headless mode defaults
ENV DISPLAY=""
ENV HEADLESS=1
ENV LIVESTREAM=0

WORKDIR /opt/isaaclab

ENTRYPOINT ["./isaaclab.sh", "-p"]
```

### Headless Execution

Isaac Sim supports headless rendering via:
- **`--headless`** flag — no GUI, uses GPU for offscreen rendering (Vulkan)
- **`--enable livestream`** — optional WebRTC streaming for remote monitoring

```bash
# Training run (headless)
docker run --gpus all --rm \
  -v /data/output:/output \
  my-isaac-lab:latest \
  source/standalone/workflows/rsl_rl/train.py \
  --task Isaac-PrinterArm-v0 \
  --headless \
  --num_envs 1024 \
  --max_iterations 5000

# Synthetic data generation (headless)
docker run --gpus all --rm \
  -v /data/datasets:/output \
  my-isaac-lab:latest \
  source/standalone/workflows/replicator/generate.py \
  --task Isaac-PrinterArm-DataGen-v0 \
  --headless \
  --num_frames 100000 \
  --output_dir /output
```

### Key Container Requirements
- **NVIDIA Container Toolkit** (`nvidia-docker2`) must be installed on host
- **Vulkan ICD** — Isaac Sim needs Vulkan even headless; the NGC container includes this
- **Shared memory:** Use `--shm-size=16g` for parallel envs (Isaac Sim uses shared memory heavily)
- **Storage:** Mount fast NVMe for USD asset loading (`/tmp` or instance store)

### NGC Authentication

```bash
# Login to NGC registry
docker login nvcr.io -u '$oauthtoken' -p <NGC_API_KEY>

# Pull base image
docker pull nvcr.io/nvidia/isaac-sim:4.5.0
```

---

## 3. Data Egress Strategy

Synthetic datasets from Isaac Lab (RGB images, depth maps, segmentation masks, joint states) can be large.

### Estimated Data Volumes

| Output Type | Per Frame | 100K Frames |
|-------------|-----------|-------------|
| RGB (1024×1024 PNG) | ~3 MB | ~300 GB |
| Depth (EXR) | ~4 MB | ~400 GB |
| Segmentation mask | ~0.5 MB | ~50 GB |
| Joint state CSV | ~1 KB | ~100 MB |
| **Total (all modalities)** | ~7.5 MB | **~750 GB** |

### Egress Approaches

1. **S3 Direct Upload (Recommended)**
   - Write output directly to S3 from within the container using `boto3` or `aws s3 sync`
   - **No egress cost** within same region (EC2 → S3)
   - Enable S3 Transfer Acceleration for cross-region if needed
   - Use S3 Intelligent-Tiering for datasets accessed intermittently

2. **Compression Pipeline**
   ```bash
   # In-container: compress before upload
   # Use JPEG for RGB (10× smaller), keep EXR for depth
   # Tar + zstd for batch upload
   tar -cf - /output/batch_001/ | zstd -3 -T0 | \
     aws s3 cp - s3://printer-arm-datasets/batch_001.tar.zst
   ```

3. **Instance Store → S3 Pattern**
   - Use NVMe instance store (`g5` has up to 3.8 TB) as scratch
   - Generate data to local NVMe (fast I/O)
   - Background sync to S3 while next batch generates
   - ~10 Gbps network on g5 instances

4. **Format Optimization**
   - Store RGB as WebP or JPEG (lossy OK for training) — 5-10× smaller
   - Use HDF5 or TFRecord for batched structured data
   - Consider Parquet for tabular joint/action data

### Cost Estimate (Data Transfer)

| Scenario | Volume | Cost |
|----------|--------|------|
| EC2 → S3 (same region) | Any | **Free** |
| S3 → Internet | 750 GB | ~$67 (first 10TB @ $0.09/GB) |
| S3 → S3 (cross-region) | 750 GB | ~$15 ($0.02/GB) |

**Tip:** Keep everything in one region. Download final trained models (small) not datasets.

---

## 4. Deployment Configuration

### Terraform Configuration

```hcl
# terraform/main.tf — Isaac Lab Training Infrastructure

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = "us-west-2"  # Good GPU Spot availability
}

# --- S3 Bucket for Datasets ---
resource "aws_s3_bucket" "datasets" {
  bucket = "printer-arm-isaac-datasets"
}

resource "aws_s3_bucket_lifecycle_configuration" "datasets_lifecycle" {
  bucket = aws_s3_bucket.datasets.id
  rule {
    id     = "archive-old"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}

# --- IAM Role for EC2 ---
resource "aws_iam_role" "isaac_runner" {
  name = "isaac-lab-runner"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  role       = aws_iam_role.isaac_runner.name
  policy_arn = "arn:aws:iam::policy/AmazonS3FullAccess"
}

resource "aws_iam_instance_profile" "isaac_runner" {
  name = "isaac-lab-runner"
  role = aws_iam_role.isaac_runner.name
}

# --- Security Group ---
resource "aws_security_group" "isaac" {
  name        = "isaac-lab-sg"
  description = "SSH + optional livestream"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  # WebRTC livestream (optional monitoring)
  ingress {
    from_port   = 49100
    to_port     = 49100
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Launch Template (Spot) ---
resource "aws_launch_template" "isaac_lab" {
  name          = "isaac-lab-training"
  image_id      = data.aws_ami.deep_learning.id
  instance_type = var.instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.isaac_runner.name
  }

  vpc_security_group_ids = [aws_security_group.isaac.id]
  key_name               = var.ssh_key_name

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 200
      volume_type           = "gp3"
      iops                  = 6000
      throughput            = 400
      delete_on_termination = true
    }
  }

  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -e

    # Install NVIDIA Container Toolkit (if not in AMI)
    if ! command -v nvidia-container-toolkit &> /dev/null; then
      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
      curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
      apt-get update && apt-get install -y nvidia-container-toolkit
      nvidia-ctk runtime configure --runtime=docker
      systemctl restart docker
    fi

    # Login to NGC
    echo "${var.ngc_api_key}" | docker login nvcr.io -u '$oauthtoken' --password-stdin

    # Pull Isaac Lab container
    docker pull ${var.isaac_container}

    # Signal ready
    touch /tmp/isaac-ready
  EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name    = "isaac-lab-training"
      Project = "3d-printer-automation-arm"
    }
  }
}

# --- Spot Fleet ---
resource "aws_spot_fleet_request" "training" {
  iam_fleet_role                      = aws_iam_role.spot_fleet.arn
  target_capacity                     = var.num_instances
  terminate_instances_with_expiration = true
  valid_until                         = timeadd(timestamp(), "24h")

  launch_template_config {
    launch_template_specification {
      id      = aws_launch_template.isaac_lab.id
      version = "$Latest"
    }

    overrides {
      instance_type = "g5.xlarge"
    }
    overrides {
      instance_type = "g5.2xlarge"
    }
  }
}

# --- Data Sources ---
data "aws_ami" "deep_learning" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }
}

# --- Variables ---
variable "instance_type"   { default = "g5.xlarge" }
variable "admin_cidr"      { default = "0.0.0.0/0" }
variable "ssh_key_name"    { type = string }
variable "ngc_api_key"     { type = string, sensitive = true }
variable "isaac_container" { default = "nvcr.io/nvidia/isaac-sim:4.5.0" }
variable "num_instances"   { default = 1 }

# --- Outputs ---
output "s3_bucket" { value = aws_s3_bucket.datasets.bucket }
```

### Quick-Start Script (No Terraform)

```bash
#!/bin/bash
# quick-launch.sh — Launch a Spot g5 instance for Isaac Lab training

INSTANCE_TYPE="g5.xlarge"
AMI_ID="ami-xxxxxxxxx"  # Deep Learning AMI, us-west-2
KEY_NAME="your-key"
SPOT_PRICE="0.50"

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --instance-market-options '{"MarketType":"spot","SpotOptions":{"MaxPrice":"'$SPOT_PRICE'","SpotInstanceType":"one-time"}}' \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":200,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=isaac-lab-training}]' \
  --query 'Instances[0].InstanceId' --output text)

echo "Launched: $INSTANCE_ID"
echo "Waiting for running state..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "SSH: ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
```

---

## 5. Workflow Summary

```
┌─────────────────────────────────────────────────────┐
│  Local Dev (Mac mini)                               │
│  ─ Design USD assets, env configs                   │
│  ─ Push to Git                                      │
└──────────────┬──────────────────────────────────────┘
               │ git push / docker push
               ▼
┌─────────────────────────────────────────────────────┐
│  AWS Spot g5.xlarge (or g5.12xlarge)                │
│  ─ Pull NGC Isaac Sim container                     │
│  ─ Run headless training (--headless --num_envs N)  │
│  ─ Generate synthetic data via Replicator           │
│  ─ Stream results → S3                              │
└──────────────┬──────────────────────────────────────┘
               │ aws s3 sync
               ▼
┌─────────────────────────────────────────────────────┐
│  S3 Bucket (same region)                            │
│  ─ Trained checkpoints (.pt)                        │
│  ─ Synthetic datasets (images, depth, labels)       │
│  ─ Logs & metrics (TensorBoard)                     │
└──────────────┬──────────────────────────────────────┘
               │ download models only (~MBs)
               ▼
┌─────────────────────────────────────────────────────┐
│  Local / Edge Deployment                            │
│  ─ Deploy trained policy to real arm                │
└─────────────────────────────────────────────────────┘
```

---

## 6. Cost Estimates (Monthly)

| Scenario | Instance | Hours/mo | Spot $/hr | Compute | Storage (S3) | **Total** |
|----------|----------|----------|-----------|---------|-------------|-----------|
| Light dev | g5.xlarge | 40 | ~$0.40 | $16 | $5 | **~$21** |
| Regular training | g5.2xlarge | 100 | ~$0.50 | $50 | $20 | **~$70** |
| Heavy data gen | g5.12xlarge | 80 | ~$2.30 | $184 | $50 | **~$234** |
| Full-scale | p4d.24xlarge | 40 | ~$12.00 | $480 | $100 | **~$580** |

**Spot pricing** varies; numbers above are approximate averages for us-west-2.

---

## 7. Key Considerations

1. **Spot Interruption Handling:** Use checkpointing (save every N iterations). Isaac Lab supports `--checkpoint_path` for resuming.
2. **AMI Choice:** AWS Deep Learning AMI comes with NVIDIA drivers pre-installed — saves 10-15 min setup.
3. **Isaac Sim Version Pinning:** Always pin the NGC container tag. Breaking changes between versions are common.
4. **Vulkan Validation:** Headless still needs Vulkan. If you see "VkResult" errors, ensure the NVIDIA driver is ≥535 and the container has `libnvidia-gl`.
5. **Multi-GPU Scaling:** Isaac Lab scales well across GPUs for parallel envs. Use `--distributed` or `--multi_gpu` flags when available.
