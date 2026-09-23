package main

import (
	"bufio"
	"encoding/json"
	"runtime"
	"strings"
	"testing"
)

func stable(product, version, tag string) []byte {
	repo := "aeloon-lite-ui"
	if product == "runtime" {
		repo = "aeloon-lite-runtime"
	}
	return []byte("# aeloon-release-v2\n# product=" + product + "\n# version=" + version +
		"\n# release=" + tag + "\n# source=AetherHeart-AI/" + repo + "@" + strings.Repeat("a", 40) + "\n")
}

func TestParseStableChannel(t *testing.T) {
	for _, value := range []struct{ product, version, tag string }{
		{"desktop", "0.4.1", "v0.4.1"},
		{"runtime", "0.4.7", "v0.4.1"},
		{"runtime", "0.4.8", "runtime-v0.4.8"},
	} {
		parsed, err := parseChannel(stable(value.product, value.version, value.tag), value.product)
		if err != nil || parsed.Tag != value.tag {
			t.Fatalf("parseChannel(%q): %+v, %v", value.tag, parsed, err)
		}
	}
	if _, err := parseChannel(stable("desktop", "0.4.1", "v0.4.2"), "desktop"); err == nil {
		t.Fatal("accepted mismatched desktop version")
	}
	if _, err := parseChannel(append(stable("desktop", "0.4.1", "v0.4.1"), []byte("# release=v9.9.9\n")...), "desktop"); err == nil {
		t.Fatal("accepted duplicate release field")
	}
}

func TestReleaseValidation(t *testing.T) {
	good := release{Schema: 1, Tag: "v0.4.1", Assets: []asset{{Name: "a", Size: 42, Digest: "sha256:" + strings.Repeat("a", 64)}}}
	data, _ := json.Marshal(good)
	if _, err := parseRelease(data, "mirror", "v0.4.1"); err != nil {
		t.Fatal(err)
	}
	good.Assets = append(good.Assets, good.Assets[0])
	data, _ = json.Marshal(good)
	if _, err := parseRelease(data, "mirror", "v0.4.1"); err == nil {
		t.Fatal("accepted duplicate asset")
	}
	github := release{TagName: "v0.4.1", Draft: true, Assets: []asset{{Name: "a", Size: 42, Digest: "sha256:" + strings.Repeat("a", 64)}}}
	data, _ = json.Marshal(github)
	if _, err := parseRelease(data, "github", "v0.4.1"); err == nil {
		t.Fatal("accepted draft GitHub Release")
	}
}

func TestMenusAndEmbeddedScripts(t *testing.T) {
	if !strings.Contains(desktopShell, "--source") || !strings.Contains(serverShell, "--source") || !strings.Contains(desktopPowerShell, "-Source") {
		t.Fatal("embedded installer scripts do not include source selection")
	}
	choice, err := choose(bufio.NewReader(strings.NewReader("\n")), "test", []string{"mirror", "github"}, 1)
	if err != nil || choice != 1 {
		t.Fatalf("default choice = %d, %v", choice, err)
	}
	if _, err := choose(bufio.NewReader(strings.NewReader("3\n")), "test", []string{"mirror", "github"}, 1); err == nil {
		t.Fatal("accepted unsupported menu choice")
	}
	if _, err := platform(); err != nil {
		if runtime.GOOS == "windows" || runtime.GOOS == "linux" || runtime.GOOS == "darwin" && runtime.GOARCH == "arm64" {
			t.Fatal(err)
		}
	}
}

func TestPlatformMenus(t *testing.T) {
	input := "1\n2\n2\n"
	if runtime.GOOS == "linux" {
		input += "1\n"
	}
	selected, err := getChoice(bufio.NewReader(strings.NewReader(input)))
	if err != nil {
		t.Fatal(err)
	}
	if selected.Product != "desktop" || selected.Source != "github" || selected.Action != "overwrite" {
		t.Fatalf("unexpected desktop menu selection: %+v", selected)
	}
	if runtime.GOOS == "linux" {
		selected, err = getChoice(bufio.NewReader(strings.NewReader("2\n\n")))
		if err != nil || selected.Product != "runtime" || selected.Source != "mirror" {
			t.Fatalf("unexpected server menu selection: %+v, %v", selected, err)
		}
	}
}
