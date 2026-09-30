#!/bin/bash
set -e

# Colored Console Output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=====================================================${NC}"
echo -e "${CYAN}     Tiny Print iOS Native .IPA Build Script         ${NC}"
echo -e "${CYAN}=====================================================${NC}"

# Check for macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ Error: iOS .ipa files can only be built on macOS!${NC}"
    exit 1
fi

# Dynamically extract version from pubspec.yaml
VERSION=$(grep -m 1 "^version:" pubspec.yaml | cut -d ' ' -f 2 | cut -d '+' -f 1)
VERSION=${VERSION:-"1.0.0"}

echo -e "${GREEN}📦 Target App Version:${NC} ${YELLOW}$VERSION${NC}"
echo -e "${GREEN}⚡ Impeller / Metal GPU Engine:${NC} ${YELLOW}ENABLED (Release Mode)${NC}"

OUTPUT_DIR="releases"
mkdir -p "$OUTPUT_DIR"

echo -e "\n${YELLOW}Select build option:${NC}"
echo "1) Development Signed .ipa (For AltStore, SideStore, Sideloadly, or Apple Configurator)"
echo "2) Unsigned .ipa (For 3rd-party web signers: Signulous, MapleSign, Scarlet)"
echo "3) Direct Wireless Deploy to Sajjad's iPhone (Installs instantly over Wi-Fi)"
echo "4) Build Both Signed and Unsigned .ipa files"
read -p "Enter choice [1-4] (default: 1): " choice
choice=${choice:-1}

clean_build() {
    echo -e "\n${CYAN}🧹 Cleaning previous build artifacts...${NC}"
    flutter clean
    flutter pub get
}

package_ipa() {
    local APP_PATH="build/ios/iphoneos/Runner.app"
    local DEST_IPA="$1"

    if [ ! -d "$APP_PATH" ]; then
        echo -e "${RED}❌ Error: Runner.app not found at $APP_PATH${NC}"
        exit 1
    fi

    echo -e "${CYAN}📦 Packaging Runner.app into .ipa format...${NC}"
    local TMP_DIR=$(mktemp -d)
    mkdir -p "$TMP_DIR/Payload"
    cp -r "$APP_PATH" "$TMP_DIR/Payload/"

    (cd "$TMP_DIR" && zip -qr "app.ipa" Payload)
    mv "$TMP_DIR/app.ipa" "$DEST_IPA"
    rm -rf "$TMP_DIR"

    local SIZE=$(du -h "$DEST_IPA" | cut -f1)
    echo -e "${GREEN}✅ .IPA Created:${NC} $DEST_IPA (${YELLOW}$SIZE${NC})"
}

build_signed_ipa() {
    echo -e "\n${CYAN}🔨 Building Development Signed iOS Application...${NC}"
    flutter build ios --release

    local DEST="$OUTPUT_DIR/TinyPOS-v${VERSION}-signed.ipa"
    package_ipa "$DEST"
}

build_unsigned_ipa() {
    echo -e "\n${CYAN}🔨 Building Unsigned iOS Application (for web/cloud signing)...${NC}"
    flutter build ios --release --no-codesign

    local DEST="$OUTPUT_DIR/TinyPOS-v${VERSION}-unsigned.ipa"
    package_ipa "$DEST"
}

deploy_wireless() {
    echo -e "\n${CYAN}🚀 Installing directly to Sajjad's iPhone over Wi-Fi...${NC}"
    flutter run --release -d "00008130-000565A922F3803A"
}

case $choice in
    1)
        clean_build
        build_signed_ipa
        ;;
    2)
        clean_build
        build_unsigned_ipa
        ;;
    3)
        deploy_wireless
        ;;
    4)
        clean_build
        build_signed_ipa
        build_unsigned_ipa
        ;;
    *)
        echo -e "${RED}Invalid choice! Exiting.${NC}"
        exit 1
        ;;
esac

echo -e "\n${CYAN}=====================================================${NC}"
echo -e "${GREEN}🎉 Build Complete! Artifacts saved in:${NC} ${YELLOW}$OUTPUT_DIR/${NC}"
ls -lh "$OUTPUT_DIR" | grep -i "\.ipa" || true
echo -e "${CYAN}=====================================================${NC}"
