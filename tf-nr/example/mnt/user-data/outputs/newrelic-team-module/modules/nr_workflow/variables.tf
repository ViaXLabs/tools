variable "account_id"               { type = string }
variable "team"                     { type = string }
variable "environment"              { type = string }
variable "channel_id"               { type = string }
variable "extra_tags"               { type = map(string); default = {} }
variable "enable_nerdgraph_tagging" { type = bool; default = true }
variable "nr_api_key"               { type = string; default = ""; sensitive = true }
variable "nr_region"                { type = string; default = "US" }
variable "script_file" {
  description = "Full path to nr_tag_resources.py"
  type        = string
  default     = "nr_tag_resources.py"
}
variable "create_muting_rule"       { type = bool; default = false }
variable "muting_rule_enabled"      { type = bool; default = false }
variable "muting_schedule" {
  type = object({
    start_time         = string
    end_time           = string
    time_zone          = string
    repeat             = optional(string)
    weekly_repeat_days = optional(list(string))
    repeat_count       = optional(number)
  })
  default = null
}
