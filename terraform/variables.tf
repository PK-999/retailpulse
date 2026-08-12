variable "project_name" {
  description = "Lowercase project prefix used in Azure resource names."
  type        = string
  default     = "retailpulse"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "centralindia"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "tags" {
  type    = map(string)
  default = { project = "RetailPulse", managed_by = "Terraform" }
}
