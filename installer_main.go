package main

import (
	"bufio"
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const mirrorRoot = "https://downloads.aeloon-lite.aetherheart.com"
const repository = "AetherHeart-AI/aeloon-lite"

//go:embed install.sh
var desktopShell string

//go:embed install.ps1
var desktopPowerShell string

//go:embed install-server.sh
var serverShell string

type channel struct {
	Product string
	Version string
	Tag     string
}

type asset struct {
	Name   string `json:"name"`
	Size   int64  `json:"size"`
	Digest string `json:"digest"`
}

type release struct {
	Schema     int     `json:"schema"`
	Tag        string  `json:"tag"`
	TagName    string  `json:"tag_name"`
	Draft      bool    `json:"draft"`
	Prerelease bool    `json:"prerelease"`
	Assets     []asset `json:"assets"`
}

type installChoice struct {
	Product string
	Source  string
	Action  string
	Format  string
}

var stableVersion = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`)
var digestPattern = regexp.MustCompile(`^sha256:[a-f0-9]{64}$`)
var clientPattern = regexp.MustCompile(`^aeloon-client-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz$`)
var commitPattern = regexp.MustCompile(`^[0-9a-f]{40}$`)

func parseChannel(data []byte, product string) (channel, error) {
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) != 5 || strings.TrimSuffix(lines[0], "\r") != "# aeloon-release-v2" {
		return channel{}, errors.New("unsupported stable channel format")
	}
	values := map[string]string{}
	for _, line := range lines[1:] {
		line = strings.TrimSuffix(line, "\r")
		if !strings.HasPrefix(line, "# ") {
			return channel{}, errors.New("invalid stable channel line")
		}
		key, value, ok := strings.Cut(strings.TrimPrefix(line, "# "), "=")
		if !ok || values[key] != "" {
			return channel{}, errors.New("duplicate or invalid stable channel field")
		}
		values[key] = value
	}
	version := values["version"]
	tag := values["release"]
	validTag := tag == "v"+version
	if product == "runtime" {
		validTag = (strings.HasPrefix(tag, "v") && stableVersion.MatchString(strings.TrimPrefix(tag, "v"))) ||
			(tag == "runtime-v"+version)
	}
	expectedSource := "AetherHeart-AI/aeloon-lite-ui@"
	if product == "runtime" {
		expectedSource = "AetherHeart-AI/aeloon-lite-runtime@"
	}
	if values["product"] != product || !stableVersion.MatchString(version) || !validTag {
		return channel{}, errors.New("stable channel identity is inconsistent")
	}
	if !strings.HasPrefix(values["source"], expectedSource) || !commitPattern.MatchString(strings.TrimPrefix(values["source"], expectedSource)) {
		return channel{}, errors.New("stable channel source is invalid")
	}
	return channel{Product: product, Version: version, Tag: tag}, nil
}

func channelURL(source, product string) string {
	if source == "mirror" {
		return mirrorRoot + "/channels/" + product + "/stable"
	}
	return "https://raw.githubusercontent.com/" + repository + "/main/channels/" + product + "/stable"
}

func releaseURL(source, tag string) string {
	if source == "mirror" {
		return mirrorRoot + "/releases/" + tag + "/manifest.json"
	}
	return "https://api.github.com/repos/" + repository + "/releases/tags/" + tag
}

func fetch(ctx context.Context, url string) ([]byte, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("User-Agent", "aeloon-installer")
	request.Header.Set("Cache-Control", "no-cache")
	client := &http.Client{Timeout: 30 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s returned HTTP %d", url, response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024+1))
	if err != nil {
		return nil, err
	}
	if len(data) > 1024*1024 {
		return nil, errors.New("release metadata is too large")
	}
	return data, nil
}

func parseRelease(data []byte, source, tag string) (release, error) {
	var value release
	if err := json.Unmarshal(data, &value); err != nil {
		return release{}, err
	}
	if source == "mirror" {
		if value.Schema != 1 || value.Tag != tag {
			return release{}, errors.New("invalid mirror manifest identity")
		}
	} else if value.TagName != tag || value.Draft || value.Prerelease {
		return release{}, errors.New("invalid GitHub Release identity")
	}
	names := map[string]bool{}
	for _, item := range value.Assets {
		if item.Name == "" || names[item.Name] || item.Size <= 0 || !digestPattern.MatchString(item.Digest) {
			return release{}, errors.New("invalid or duplicate Release asset")
		}
		names[item.Name] = true
	}
	return value, nil
}

func oneAsset(value release, name string) (asset, error) {
	for _, item := range value.Assets {
		if item.Name == name {
			return item, nil
		}
	}
	return asset{}, fmt.Errorf("Release asset is missing: %s", name)
}

func oneClient(value release) (asset, error) {
	var found asset
	for _, item := range value.Assets {
		if clientPattern.MatchString(item.Name) {
			if found.Name != "" {
				return asset{}, errors.New("Release has multiple client archives")
			}
			found = item
		}
	}
	if found.Name == "" {
		return asset{}, errors.New("Runtime stable has no matched client archive")
	}
	return found, nil
}

func choose(reader *bufio.Reader, title string, options []string, defaultChoice int) (int, error) {
	fmt.Println("\n" + title)
	for index, option := range options {
		fmt.Printf("  %d. %s\n", index+1, option)
	}
	fmt.Printf("选择 [%d]: ", defaultChoice)
	line, err := reader.ReadString('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return 0, err
	}
	line = strings.TrimSpace(line)
	if errors.Is(err, io.EOF) && line == "" {
		return 0, errors.New("没有可用的交互输入")
	}
	if line == "" {
		return defaultChoice, nil
	}
	value, parseErr := strconv.Atoi(line)
	if parseErr != nil || value < 1 || value > len(options) {
		return 0, errors.New("无效选择")
	}
	return value, nil
}

func platform() (string, error) {
	switch runtime.GOOS + "/" + runtime.GOARCH {
	case "windows/amd64":
		return "Windows x64", nil
	case "darwin/arm64":
		return "macOS ARM64", nil
	case "linux/amd64":
		return "Linux x86_64", nil
	case "linux/arm64":
		return "Linux ARM64", nil
	default:
		return "", fmt.Errorf("不支持的平台：%s/%s", runtime.GOOS, runtime.GOARCH)
	}
}

func linuxFormat() string {
	data, err := os.ReadFile("/etc/os-release")
	if err == nil {
		lower := strings.ToLower(string(data))
		if strings.Contains(lower, "ubuntu") || strings.Contains(lower, "debian") || strings.Contains(lower, "kylin") {
			return "deb"
		}
		if strings.Contains(lower, "fedora") || strings.Contains(lower, "rhel") || strings.Contains(lower, "centos") || strings.Contains(lower, "suse") {
			return "rpm"
		}
	}
	if _, err := exec.LookPath("apt-get"); err == nil {
		return "deb"
	}
	return "rpm"
}

func getChoice(reader *bufio.Reader) (installChoice, error) {
	choice := installChoice{}
	modes := []string{"本机 Desktop"}
	if runtime.GOOS == "linux" {
		modes = append(modes, "当前 Linux 主机上的 Runtime Server")
	}
	mode, err := choose(reader, "安装内容", modes, 1)
	if err != nil {
		return choice, err
	}
	choice.Product = "desktop"
	if mode == 2 {
		choice.Product = "runtime"
	}
	source, err := choose(reader, "下载来源", []string{"官方镜像（推荐）", "GitHub"}, 1)
	if err != nil {
		return choice, err
	}
	choice.Source = "mirror"
	if source == 2 {
		choice.Source = "github"
	}
	if choice.Product == "desktop" {
		action, err := choose(reader, "已有安装时", []string{"更新（已是最新版则跳过）", "覆盖重装", "保留现有版本"}, 1)
		if err != nil {
			return choice, err
		}
		choice.Action = []string{"update", "overwrite", "skip"}[action-1]
		if runtime.GOOS == "linux" {
			preferred := linuxFormat()
			defaultChoice := 1
			if preferred == "rpm" {
				defaultChoice = 2
			}
			format, err := choose(reader, "Linux 安装包格式", []string{"DEB（Debian/Ubuntu）", "RPM（Fedora/RHEL/SUSE）"}, defaultChoice)
			if err != nil {
				return choice, err
			}
			choice.Format = []string{"deb", "rpm"}[format-1]
		}
	}
	return choice, nil
}

func desktopAsset(version, format string) string {
	switch runtime.GOOS {
	case "windows":
		return "aeloon-lite-" + version + "-x64.exe"
	case "darwin":
		return "aeloon-lite-" + version + "-arm64.dmg"
	default:
		arch := "x86_64"
		if runtime.GOARCH == "arm64" {
			arch = "arm64"
		}
		return "aeloon-lite-" + version + "-" + arch + "." + format
	}
}

func runtimeAsset() string {
	arch := "x86_64"
	if runtime.GOARCH == "arm64" {
		arch = "aarch64"
	}
	return "aeloon-runtime-linux-" + arch + ".tar.gz"
}

func runInstall(ctx context.Context, choice installChoice) (string, error) {
	channelData, err := fetch(ctx, channelURL(choice.Source, choice.Product))
	if err != nil {
		return "network", err
	}
	stable, err := parseChannel(channelData, choice.Product)
	if err != nil {
		return "integrity", err
	}
	releaseData, err := fetch(ctx, releaseURL(choice.Source, stable.Tag))
	if err != nil {
		return "network", err
	}
	metadata, err := parseRelease(releaseData, choice.Source, stable.Tag)
	if err != nil {
		return "integrity", err
	}
	fmt.Printf("\n将安装 %s %s，来源：%s\n", choice.Product, stable.Version, choice.Source)
	var selected asset
	var client asset
	if choice.Product == "desktop" {
		selected, err = oneAsset(metadata, desktopAsset(stable.Version, choice.Format))
	} else {
		selected, err = oneAsset(metadata, runtimeAsset())
		if err == nil {
			client, err = oneClient(metadata)
		}
	}
	if err != nil {
		return "integrity", err
	}
	temporary, err := os.MkdirTemp("", "aeloon-installer-")
	if err != nil {
		return "other", err
	}
	defer os.RemoveAll(temporary)
	channelPath := filepath.Join(temporary, "stable")
	if err = os.WriteFile(channelPath, channelData, 0600); err != nil {
		return "other", err
	}
	releasePath := filepath.Join(temporary, "release.json")
	if err = os.WriteFile(releasePath, releaseData, 0600); err != nil {
		return "other", err
	}
	script := desktopShell
	scriptName := "install.sh"
	if choice.Product == "runtime" {
		script = serverShell
		scriptName = "install-server.sh"
	} else if runtime.GOOS == "windows" {
		script = desktopPowerShell
		scriptName = "install.ps1"
	}
	scriptPath := filepath.Join(temporary, scriptName)
	if err = os.WriteFile(scriptPath, []byte(script), 0700); err != nil {
		return "other", err
	}
	var command *exec.Cmd
	if runtime.GOOS == "windows" {
		command = exec.CommandContext(ctx, "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath, "-Source", choice.Source, "-IfInstalled", choice.Action)
	} else {
		args := []string{scriptPath, "--source", choice.Source}
		if choice.Product == "desktop" {
			args = append(args, "--if-installed", choice.Action)
			if choice.Format != "" {
				args = append(args, "--format", choice.Format)
			}
		}
		command = exec.CommandContext(ctx, "/bin/sh", args...)
	}
	command.Stdin = os.Stdin
	var output bytes.Buffer
	command.Stdout = io.MultiWriter(os.Stdout, &output)
	command.Stderr = io.MultiWriter(os.Stderr, &output)
	command.Env = append(os.Environ(),
		"AELOON_CHANNEL_FILE="+channelPath,
		"AELOON_RELEASE_JSON_FILE="+releasePath,
		"AELOON_EXPECTED_ASSET_SHA256="+selected.Digest,
		fmt.Sprintf("AELOON_EXPECTED_ASSET_SIZE=%d", selected.Size),
		"AELOON_EXPECTED_RUNTIME_SHA256="+selected.Digest,
		fmt.Sprintf("AELOON_EXPECTED_RUNTIME_SIZE=%d", selected.Size),
		"AELOON_EXPECTED_CLIENT_NAME="+client.Name,
		"AELOON_EXPECTED_CLIENT_SHA256="+client.Digest,
		fmt.Sprintf("AELOON_EXPECTED_CLIENT_SIZE=%d", client.Size),
	)
	if err := command.Run(); err != nil {
		lower := strings.ToLower(output.String())
		if strings.Contains(lower, "digest") || strings.Contains(lower, "checksum") || strings.Contains(lower, "sha-256") || strings.Contains(lower, "size mismatch") || strings.Contains(lower, "size differs") {
			return "integrity", err
		}
		if strings.Contains(lower, "curl:") || strings.Contains(lower, "could not resolve") || strings.Contains(lower, "invoke-webrequest") || strings.Contains(lower, "invoke-restmethod") || strings.Contains(lower, "http ") {
			return "network", err
		}
		return "other", err
	}
	return "", nil
}

func main() {
	version := flag.Bool("version", false, "show the embedded installer commit")
	flag.Parse()
	if *version {
		fmt.Println("Aeloon Installer", buildCommit)
		return
	}
	name, err := platform()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	fmt.Printf("Aeloon 安装器 · %s\n", name)
	reader := bufio.NewReader(os.Stdin)
	choice, err := getChoice(reader)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	confirmation, err := choose(reader, "开始安装？", []string{"开始", "取消"}, 1)
	if err != nil || confirmation == 2 {
		fmt.Println("已取消。")
		return
	}
	for {
		kind, err := runInstall(context.Background(), choice)
		if err == nil {
			fmt.Println("\n完成。")
			return
		}
		fmt.Fprintln(os.Stderr, "\n安装失败：", err)
		if kind == "integrity" {
			fmt.Fprintln(os.Stderr, "校验失败，已停止安装。请检查发布资产。")
			os.Exit(1)
		}
		if kind != "network" {
			os.Exit(1)
		}
		next, chooseErr := choose(reader, "下一步", []string{"重试当前来源", "切换来源后重试", "退出"}, 1)
		if chooseErr != nil || next == 3 {
			os.Exit(1)
		}
		if next == 2 {
			if choice.Source == "mirror" {
				choice.Source = "github"
			} else {
				choice.Source = "mirror"
			}
		}
	}
}

var buildCommit = "development"
