# Local state for staging bootstrap. Do not commit terraform.tfstate*.
#
# Production (later):
# terraform {
#   backend "s3" {
#     bucket   = "<state-bucket>"
#     key      = "mana-guruji/production/terraform.tfstate"
#     region   = "ap-hyderabad-1"
#     endpoint = "https://<namespace>.compat.objectstorage.ap-hyderabad-1.oraclecloud.com"
#     ...
#   }
# }

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
