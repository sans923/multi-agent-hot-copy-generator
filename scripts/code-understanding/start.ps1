param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("deepwiki", "gitdiagram")]
    [string]$Tool,

    [Parameter(Position = 1)]
    [ValidateSet("build", "up", "down", "logs", "status")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"

$toolingRoot = if ($env:WORKSPACE_TOOLING_ROOT) {
    $env:WORKSPACE_TOOLING_ROOT
} else {
    "D:\workspace\_tooling"
}

$definitions = @{
    deepwiki = @{
        Source = Join-Path $toolingRoot "tools\gui\deepwiki-open"
        Config = Join-Path $toolingRoot "config\code-understanding\deepwiki.env"
        Cache = Join-Path $toolingRoot "cache\deepwiki"
        Image = "workspace/deepwiki-open:local"
        Container = "workspace-deepwiki-open"
        Ports = @("8001:8001", "3001:3000")
    }
    gitdiagram = @{
        Source = Join-Path $toolingRoot "tools\gui\gitdiagram"
        Config = Join-Path $toolingRoot "config\code-understanding\gitdiagram.env"
        Cache = Join-Path $toolingRoot "cache\gitdiagram"
        Image = "workspace/gitdiagram:local"
        Container = "workspace-gitdiagram"
        Ports = @("3002:3000")
    }
}

$definition = $definitions[$Tool]

if (-not (Test-Path -LiteralPath $definition.Source)) {
    throw "Tool source is missing: $($definition.Source)"
}

function Test-Image {
    docker image inspect $definition.Image *> $null
    return $LASTEXITCODE -eq 0
}

function Build-Image {
    docker build --tag $definition.Image $definition.Source
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed for $Tool."
    }
}

switch ($Action) {
    "build" {
        Build-Image
    }
    "up" {
        if (-not (Test-Path -LiteralPath $definition.Config)) {
            $template = Join-Path $toolingRoot "config\templates\code-understanding\$Tool.env.example"
            throw "Missing model configuration. Copy '$template' to '$($definition.Config)' and add a model API key."
        }
        if (-not (Test-Image)) {
            Build-Image
        }
        New-Item -ItemType Directory -Force -Path $definition.Cache | Out-Null
        docker rm --force $definition.Container *> $null

        $arguments = @(
            "run", "--detach",
            "--name", $definition.Container,
            "--env-file", $definition.Config
        )
        foreach ($port in $definition.Ports) {
            $arguments += @("--publish", $port)
        }
        if ($Tool -eq "deepwiki") {
            $arguments += @("--volume", "$($definition.Cache):/root/.adalflow")
        }
        $arguments += $definition.Image
        docker @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start $Tool."
        }
    }
    "down" {
        docker rm --force $definition.Container
    }
    "logs" {
        docker logs --follow $definition.Container
    }
    "status" {
        docker ps --all --filter "name=$($definition.Container)"
    }
}

