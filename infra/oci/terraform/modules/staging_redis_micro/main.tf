data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "ol_x86" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = "VM.Standard.E2.1.Micro"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  ad_name  = coalesce(var.availability_domain_name, data.oci_identity_availability_domains.ads.availability_domains[0].name)
  image_id = data.oci_core_images.ol_x86.images[0].id
  cloud_init = templatefile("${path.module}/cloud-init/redis-docker.yaml.tftpl", {
    redis_image = var.redis_image
  })
}

resource "oci_core_network_security_group" "redis" {
  compartment_id = var.compartment_id
  vcn_id         = var.vcn_id
  display_name   = "${var.display_name_prefix}-redis-nsg"
}

resource "oci_core_network_security_group_security_rule" "redis_ssh" {
  for_each                  = toset(var.ssh_allowed_cidrs)
  network_security_group_id = oci_core_network_security_group.redis.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "redis_port_app_subnet" {
  network_security_group_id = oci_core_network_security_group.redis.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.redis_client_cidr
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 6379
      max = 6379
    }
  }
}

resource "oci_core_network_security_group_security_rule" "redis_port_extra" {
  for_each                  = toset(var.redis_extra_client_cidrs)
  network_security_group_id = oci_core_network_security_group.redis.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 6379
      max = 6379
    }
  }
}

resource "oci_core_instance" "redis" {
  compartment_id      = var.compartment_id
  availability_domain = local.ad_name
  display_name        = var.hostname
  shape               = "VM.Standard.E2.1.Micro"

  create_vnic_details {
    subnet_id        = var.subnet_id
    assign_public_ip = true
    hostname_label   = replace(var.hostname, ".", "-")
    nsg_ids          = [oci_core_network_security_group.redis.id]
  }

  source_details {
    source_type             = "image"
    source_id               = local.image_id
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(local.cloud_init)
  }

  freeform_tags = {
    "mana_guruji_environment" = "staging"
    "mana_guruji_fleet_host"    = var.hostname
    "mana_guruji_role"          = "cache_redis_docker"
    "mana_guruji_managed_by"    = "terraform"
  }
}
