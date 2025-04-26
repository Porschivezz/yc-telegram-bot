terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = "~> 0.89.0"
    }
  }
}

provider "yandex" {
  token     = var.yc_token
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = var.zone
}

resource "yandex_container_repository" "bot" {
  name = "${var.registry_id}/telegram-bot"
}

data "yandex_compute_image" "ubuntu" {
  family = "ubuntu-2204-lts"
}

resource "yandex_compute_instance" "bot_vm" {
  name        = "telegram-bot-vm"
  platform_id = "standard-v1"

  resources {
    cores  = 2
    memory = 2
  }

  boot_disk {
    initialize_params {
      image_id = data.yandex_compute_image.ubuntu.id
    }
  }

  network_interface {
    subnet_id = var.subnet_id
    nat       = true
  }

  metadata = {
    enable-oslogin = "false"
    ssh-keys = "ubuntu:ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCqjjCiO6Moj+OTV51QrGST1gjUyRDb7xModv8Lvog/9V5KI1hWjPdHoZn2ZeeNt17PbCPDOBO9TSCr44KjQ/+EhkzjYQGutgIejPIO7Yg5j5yQvkl/vtJ5QtLLfCZyCy6GjhOnp5k56G+/VLpOlPYZeizsBIBvf72XaUnD/WBYyxO2rxpgpMtcP51Vz2XgsxYo1hjJNjL6pUAo6s2swwRAOo5xSoRXtzjeZJzXJmZ0pzGbP0MThE+QLdaN7GA7u7OZfnHArOaikF6eJTnqHWjJ0D23RSCHowpmFTHCYrHkXu234p4y1DSFSHEzruJ+o9PkFSGA5jRdlQvZ+wP+qFYR n.zharkov92@yandex.ru"

    user-data = <<-EOC
#cloud-config
chpasswd:
  list: |
    ubuntu:SecureP@ssw0rd123
  expire: false

packages:
  - docker.io

runcmd:
  - docker login cr.yandex/${var.registry_id} -u oauth -p "${var.yc_token}"
  - docker pull cr.yandex/${var.registry_id}/telegram-bot:latest
  - docker run -d --restart unless-stopped \
      -e TELEGRAM_TOKEN="${var.telegram_token}" \
      --name telegram-bot \
      cr.yandex/${var.registry_id}/telegram-bot:latest
EOC
  }
}
