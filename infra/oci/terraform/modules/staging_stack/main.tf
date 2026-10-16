data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "ol_aarch64" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = var.operating_system_version
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  ad_name = coalesce(
    var.availability_domain_name,
    data.oci_identity_availability_domains.ads.availability_domains[0].name
  )
  image_id = data.oci_core_images.ol_aarch64.images[0].id
}

resource "oci_core_vcn" "staging" {
  compartment_id = var.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.display_name_prefix}-vcn"
  dns_label      = "stgvcn"
}

resource "oci_core_internet_gateway" "staging" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.staging.id
  display_name   = "${var.display_name_prefix}-igw"
  enabled        = true
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.staging.id
  display_name   = "${var.display_name_prefix}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.staging.id
  }
}

resource "oci_core_security_list" "staging_ssh" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.staging.id
  display_name   = "${var.display_name_prefix}-ssh"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  dynamic "ingress_security_rules" {
    for_each = var.ssh_allowed_cidrs
    content {
      protocol = "6"
      source   = ingress_security_rules.value
      tcp_options {
        min = 22
        max = 22
      }
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.staging.id
  cidr_block                 = var.subnet_cidr
  display_name               = "${var.display_name_prefix}-public"
  dns_label                  = "stgpub"
  prohibit_public_ip_on_vnic = false
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.staging_ssh.id]
}

resource "oci_core_instance" "stg_aio" {
  compartment_id      = var.compartment_id
  availability_domain = local.ad_name
  display_name        = var.hostname
  shape               = var.shape

  shape_config {
    ocpus         = var.ocpu_count
    memory_in_gbs = var.memory_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    hostname_label   = replace(var.hostname, ".", "-")
  }

  source_details {
    source_type             = "image"
    source_id               = local.image_id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }

  # OCI freeform tag keys: no '.' in key names (LaunchInstance validation).
  freeform_tags = {
    "mana_guruji_environment" = "staging"
    "mana_guruji_fleet_host"  = var.hostname
    "mana_guruji_managed_by"  = "terraform"
  }
}
