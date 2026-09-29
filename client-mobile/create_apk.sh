#!/bin/bash
set -e

# Automatically set valid JAVA_HOME on macOS if needed
if [ -x "/usr/libexec/java_home" ]; then
    export JAVA_HOME=$(/usr/libexec/java_home)
fi

# Colored Console Output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}=====================================================${NC}"
echo -e "${CYAN}   Tiny Print Native Android Multi-APK Build Script  ${NC}"
echo -e "${CYAN}=====================================================${NC}"

# Check for key.properties
if [ ! -f "key.properties" ] && [ ! -f "android/key.properties" ]; then
    echo -e "${RED}❌ Error: key.properties file not found!${NC}"
    echo -e "${YELLOW}Please create key.properties or copy key.properties.example with your keystore credentials.${NC}"
    echo -e "Example command to generate production keystore:"
    echo -e "  keytool -genkey -v -keystore tinypos-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias tinypos"
    exit 1
fi

# Ensure key.properties is accessible in android directory as well
if [ -f "key.properties" ] && [ ! -f "android/key.properties" ]; then
    cp "key.properties" "android/key.properties"
fi

# Dynamically extract version from pubspec.yaml
VERSION=$(grep -m 1 "^version:" pubspec.yaml | cut -d ' ' -f 2 | cut -d '+' -f 1)
VERSION=${VERSION:-"1.0.0"}

echo -e "${GREEN}📦 Target App Version:${NC} ${YELLOW}$VERSION${NC}"
echo -e "${GREEN}⚡ R8 Minification & Tree-Shaking:${NC} ${YELLOW}ENABLED (Release Mode)${NC}"

OUTPUT_DIR="releases"
mkdir -p "$OUTPUT_DIR"

echo -e "\n${YELLOW}Select build option:${NC}"
echo "1) Universal Signed Release APK (Single APK containing all architectures)"
echo "2) Split Architecture Release APKs (Separate small APKs for arm64-v8a, armeabi-v7a, x86_64)"
echo "3) Signed Android App Bundle (.aab) (For Google Play Store submission)"
echo "4) Build EVERYTHING (Universal APK, Split APKs, and App Bundle)"
read -p "Enter choice [1-4] (default: 4): " choice
choice=${choice:-4}

clean_build() {
    echo -e "\n${CYAN}🧹 Cleaning previous build artifacts...${NC}"
    flutter clean
    flutter pub get
}

build_universal_apk() {
    echo -e "\n${CYAN}🔨 Building Universal Signed Release APK...${NC}"
    flutter build apk --release

    SRC_APK="build/app/outputs/flutter-apk/app-release.apk"
    DEST_APK="$OUTPUT_DIR/TinyPrint-v${VERSION}-universal-signed.apk"

    if [ -f "$SRC_APK" ]; then
        cp "$SRC_APK" "$DEST_APK"
        SIZE=$(du -h "$DEST_APK" | cut -f1)
        echo -e "${GREEN}✅ Universal APK Created:${NC} $DEST_APK (${YELLOW}$SIZE${NC})"
    else
        echo -e "${RED}❌ Universal APK not found at $SRC_APK${NC}"
    fi
}

build_split_apks() {
    echo -e "\n${CYAN}🔨 Building Split Architecture Signed Release APKs...${NC}"
    flutter build apk --split-per-abi --release

    APK_DIR="build/app/outputs/flutter-apk"
    
    for abi in arm64-v8a armeabi-v7a x86_64; do
        SRC_APK="$APK_DIR/app-${abi}-release.apk"
        DEST_APK="$OUTPUT_DIR/TinyPrint-v${VERSION}-${abi}-signed.apk"
        if [ -f "$SRC_APK" ]; then
            cp "$SRC_APK" "$DEST_APK"
            SIZE=$(du -h "$DEST_APK" | cut -f1)
            echo -e "${GREEN}✅ Split APK (${abi}) Created:${NC} $DEST_APK (${YELLOW}$SIZE${NC})"
        fi
    done
}

build_appbundle() {
    echo -e "\n${CYAN}🔨 Building Native Signed App Bundle (.aab) for Google Play...${NC}"
    flutter build appbundle --release

    SRC_AAB="build/app/outputs/bundle/release/app-release.aab"
    DEST_AAB="$OUTPUT_DIR/TinyPrint-v${VERSION}-signed.aab"

    if [ -f "$SRC_AAB" ]; then
        cp "$SRC_AAB" "$DEST_AAB"
        SIZE=$(du -h "$DEST_AAB" | cut -f1)
        echo -e "${GREEN}✅ Play Store App Bundle Created:${NC} $DEST_AAB (${YELLOW}$SIZE${NC})"
    else
        echo -e "${RED}❌ App Bundle not found at $SRC_AAB${NC}"
    fi
}

case $choice in
    1)
        clean_build
        build_universal_apk
        ;;
    2)
        clean_build
        build_split_apks
        ;;
    3)
        clean_build
        build_appbundle
        ;;
    4)
        clean_build
        build_universal_apk
        build_split_apks
        build_appbundle
        ;;
    *)
        echo -e "${RED}Invalid choice! Exiting.${NC}"
        exit 1
        ;;
esac

echo -e "\n${CYAN}=====================================================${NC}"
echo -e "${GREEN}🎉 Build Complete! All native release files saved in:${NC} ${YELLOW}$OUTPUT_DIR/${NC}"
ls -lh "$OUTPUT_DIR"
echo -e "${CYAN}=====================================================${NC}"
