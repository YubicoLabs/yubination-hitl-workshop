package cmd

import (
	"fmt"
	"runtime"

	"github.com/spf13/cobra"

	"github.com/preloop/preloop/cli/internal/version"
)

// versionCmd represents the version command.
var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print version information",
	Long:  `Print the version, build info, and check for updates.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		checkUpdate, _ := cmd.Flags().GetBool("check")

		fmt.Printf("preloop version %s\n", version.Version)
		fmt.Printf("  commit: %s\n", version.Commit)
		fmt.Printf("  built:  %s\n", version.BuildDate)
		fmt.Printf("  go:     %s\n", runtime.Version())
		fmt.Printf("  os/arch: %s/%s\n", runtime.GOOS, runtime.GOARCH)

		if checkUpdate {
			fmt.Println()
			if err := version.CheckForUpdate(); err != nil {
				return fmt.Errorf("failed to check for updates: %w", err)
			}
		}

		return nil
	},
}

func init() {
	versionCmd.Flags().BoolP("check", "c", false, "check for updates")
}
