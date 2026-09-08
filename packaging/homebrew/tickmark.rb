# Formula for the donpaco13/homebrew-tickmark tap. Not active until that
# tap repo exists and this file is copied there as Formula/tickmark.rb.
#
# `sha256` below is a placeholder — after cutting a release, replace it with
# the checksum from that release's `tk.sha256` asset (release.yml computes
# and publishes it) and bump `url`/`version` together.
#
# No `depends_on "python@x.y"`: tk only needs some python3 on PATH, matching
# its own no-added-dependency stance, and both macOS and Homebrew's Linux
# images ship one.
class Tickmark < Formula
  desc "Live checklist for coding agents that don't have one"
  homepage "https://github.com/donpaco13/tickmark"
  url "https://github.com/donpaco13/tickmark/releases/download/v1.0.0/tk"
  sha256 "REPLACE_WITH_SHA256_FROM_v1.0.0_RELEASE"
  version "1.0.0"
  license "MIT"

  def install
    bin.install "tk"
  end

  test do
    system "#{bin}/tk", "--json"
  end
end
