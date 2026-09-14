# typed: strict
# frozen_string_literal: true

# Formula for the donpaco13/homebrew-tickmark tap. Not active until that
# tap repo exists and this file is copied there as Formula/tickmark.rb.
#
# When cutting a new release, update `url`, `version`, and `sha256` matching
# that release's `tk.sha256` asset (computed by release.yml).
#
# No `depends_on "python@x.y"`: tk only needs some python3 on PATH, matching
# its own no-added-dependency stance, and both macOS and Homebrew's Linux
# images ship one.
class Tickmark < Formula
  desc "Live checklist for coding agents that don't have one"
  homepage "https://github.com/donpaco13/tickmark"
  url "https://github.com/donpaco13/tickmark/releases/download/v1.0.0/tk"
  version "1.0.0"
  sha256 "fc5a0ff9007cd6280de4b4ea981ead1e96e43bba062ab8572d746143031935d3"
  license "MIT"

  def install
    bin.install "tk"
  end

  test do
    system "#{bin}/tk", "--json"
  end
end
