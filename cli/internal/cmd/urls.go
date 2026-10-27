package cmd

import (
	"fmt"
	"strings"

	"github.com/preloop/preloop/cli/internal/config"
)

func resolveConfiguredAPIURL() (string, error) {
	cfg, err := config.Resolve(FlagToken, FlagURL)
	if err != nil {
		return "", fmt.Errorf("failed to load config: %w", err)
	}
	return strings.TrimRight(cfg.APIURL, "/"), nil
}
