variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bedrock_model_id" {
  description = "Cheapest Amazon text model; available to new accounts without a use-case form."
  type        = string
  default     = "amazon.nova-micro-v1:0"
}

variable "insights_daily_cap" {
  type    = number
  default = 100
}

variable "alert_email" {
  type    = string
  default = "adelsherif8@gmail.com"
}

output "url" {
  value = aws_lambda_function_url.public.function_url
}

output "account" {
  value = data.aws_caller_identity.me.account_id
}
