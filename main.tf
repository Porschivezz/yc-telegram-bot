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
  family      = "ubuntu-2204-lts"
}

resource "yandex_compute_instance" "bot_vm" {
  name        = "telegram-bot-vm"
  platform_id = "standard-v1"

  resources {
    cores  = 1
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
    user-data = <<-EOC
      #cloud-config
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
