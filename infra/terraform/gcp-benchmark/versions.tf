terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.45"
    }

    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

