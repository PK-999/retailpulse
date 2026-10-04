variable "subscription_id" {
  description = "Azure subscription ID selected for the deployment."
  type        = string

  validation {
    condition = can(regex(
      "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
      var.subscription_id,
    ))
    error_message = "subscription_id must be an Azure subscription UUID."
  }
}

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

variable "name_suffix" {
  description = "Reviewed lowercase suffix used to make global Azure names unique."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,8}$", var.name_suffix))
    error_message = "name_suffix must contain 3-8 lowercase letters or digits."
  }
}

variable "monthly_budget_amount" {
  description = "Subscription monthly cost budget in USD. This alerts but does not stop spend."
  type        = number
  default     = 10

  validation {
    condition     = var.monthly_budget_amount >= 10
    error_message = "monthly_budget_amount must be at least 10 USD."
  }
}

variable "enable_event_hubs" {
  description = "Create the billable Event Hubs namespace and topics only for bounded streaming tests."
  type        = bool
  default     = false
}

variable "enable_databricks_workspace" {
  description = "Create the Databricks workspace and its billable managed networking only for bounded Azure demo sessions."
  type        = bool
  default     = false
}

variable "teardown_after" {
  description = "ISO date recorded in tags for the planned demo teardown."
  type        = string

  validation {
    condition     = can(regex("^20[0-9]{2}-[0-9]{2}-[0-9]{2}$", var.teardown_after))
    error_message = "teardown_after must use YYYY-MM-DD."
  }
}

variable "tags" {
  type    = map(string)
  default = { project = "RetailPulse", managed_by = "Terraform" }
}

variable "enable_cloud_monitoring" {
  description = "Opt in to one billable ADF failure metric alert for the bounded proof."
  type        = bool
  default     = false
}

variable "enable_adf_log_archive" {
  description = "Archive ADF run logs to existing same-region lake storage; storage costs apply."
  type        = bool
  default     = false
}

variable "monitor_email_receivers" {
  description = "Explicitly authorized recipients by label; empty means Azure alert state only."
  type        = map(string)
  default     = {}
  sensitive   = true

  validation {
    condition     = alltrue([for address in values(var.monitor_email_receivers) : can(regex("^[^@ ]+@[^@ ]+\\.[^@ ]+$", address))])
    error_message = "monitor_email_receivers must contain email addresses."
  }
}
