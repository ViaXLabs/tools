variable "account_id"               { type = string }
variable "team"                     { type = string }
variable "environment"              { type = string }
variable "extra_tags"               { type = map(string); default = {} }
variable "enable_nerdgraph_tagging" { type = bool; default = true }
variable "nr_api_key"               { type = string; default = ""; sensitive = true }
variable "nr_region"                { type = string; default = "US" }
variable "script_file" {
  description = "Full path to nr_tag_resources.py. Use absolute path or path relative to where terraform is run."
  type        = string
  default     = "nr_tag_resources.py"
}
