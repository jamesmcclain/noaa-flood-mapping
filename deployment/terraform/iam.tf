#
# Container Instance IAM resources
#
data "aws_iam_policy_document" "container_instance_ec2_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "container_instance_ec2" {
  name               = "ContainerInstanceProfile"
  assume_role_policy = data.aws_iam_policy_document.container_instance_ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ec2_service_role" {
  role       = aws_iam_role.container_instance_ec2.name
  policy_arn = var.aws_ec2_service_role_policy_arn
}

resource "aws_iam_instance_profile" "container_instance" {
  name = aws_iam_role.container_instance_ec2.name
  role = aws_iam_role.container_instance_ec2.name
}

data "aws_iam_policy_document" "scoped_data" {
  statement {
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:DeleteObject"
    ]

    resources = [
      "${aws_s3_bucket.data.arn}",
      "${aws_s3_bucket.data.arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "scoped_data" {
  name   = "s3ScopedDataPolicy"
  role   = aws_iam_role.container_instance_ec2.name
  policy = data.aws_iam_policy_document.scoped_data.json
}

#
# Spot Fleet IAM resources
#

data "aws_iam_policy_document" "scoped_s2_data" {
  statement {
    effect = "Allow"

    actions = [
      "s3:Get*",
      "s3:List*"
    ]

    resources = [
      "arn:aws:s3:::sentinel-inventory",
      "arn:aws:s3:::sentinel-inventory/*",
      "arn:aws:s3:::sentinel-s2-l2a",
      "arn:aws:s3:::sentinel-s2-l2a/*",
      "arn:aws:s3:::sentinel-s2-l1c",
      "arn:aws:s3:::sentinel-s2-l1c/*"
    ]
  }
}

resource "aws_iam_role_policy" "sentinel_on_aws" {
  name   = "s3Sentinel2ScopedDataPolicy"
  role   = aws_iam_role.container_instance_ec2.name
  policy = data.aws_iam_policy_document.scoped_s2_data.json
}

data "aws_iam_policy_document" "container_instance_spot_fleet_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["spotfleet.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "container_instance_spot_fleet" {
  name               = "fleetServiceRole"
  assume_role_policy = data.aws_iam_policy_document.container_instance_spot_fleet_assume_role.json
}

resource "aws_iam_role_policy_attachment" "spot_fleet_policy" {
  role       = aws_iam_role.container_instance_spot_fleet.name
  policy_arn = var.aws_spot_fleet_service_role_policy_arn
}

#
# Batch IAM resources
#
data "aws_iam_policy_document" "container_instance_batch_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["batch.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "container_instance_batch" {
  name               = "batchServiceRole"
  assume_role_policy = data.aws_iam_policy_document.container_instance_batch_assume_role.json
}

resource "aws_iam_role_policy_attachment" "batch_policy" {
  role       = aws_iam_role.container_instance_batch.name
  policy_arn = var.aws_batch_service_role_policy_arn
}

#
# ECS IAM resources
#
data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = [
      "sts:AssumeRole",
    ]
  }
}

resource "aws_iam_role" "ecs_task_execution_role" {
  name               = "ecsTaskExecutionRole"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role" "ecs_task_role" {
  name               = "ecsTaskRole"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = var.aws_ecs_task_execution_role_policy_arn
}
