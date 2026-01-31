#!/bin/bash
# ShellSensei - One-Line Installer
# Usage: curl -sSL https://raw.githubusercontent.com/n4bi10p/shellsensei/main/install.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${RED}"
cat << "EOF"
   ███████╗██╗  ██╗███████╗██╗     ██╗     ███████╗███████╗███╗   ██╗███████╗███████╗██╗
   ██╔════╝██║  ██║██╔════╝██║     ██║     ██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝██║
   ███████╗███████║█████╗  ██║     ██║     ███████╗█████╗  ██╔██╗ ██║███████╗█████╗  ██║
   ╚════██║██╔══██║██╔══╝  ██║     ██║     ╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══╝  ██║
   ███████║██║  ██║███████╗███████╗███████╗███████║███████╗██║ ╚████║███████║███████╗██║
   ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝╚═╝
EOF
echo -e "${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}System-Aware AI Terminal Assistant${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}✗ ShellSensei requires Linux. Detected: $OSTYPE${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Detected Linux system"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 is required but not installed${NC}"
    echo -e "${YELLOW}  Install with: sudo apt install python3 python3-venv python3-pip${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found"

# Installation directory
INSTALL_DIR="$HOME/.shellsensei"
REPO_URL="https://github.com/n4bi10p/shellsensei"

# Clone or update repository
echo ""
echo -e "${BLUE}[1/5]${NC} Installing ShellSensei..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}  ShellSensei already exists. Updating...${NC}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || echo -e "${YELLOW}  (Could not update, using existing version)${NC}"
elif [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}  Removing incomplete installation...${NC}"
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create virtual environment
echo ""
echo -e "${BLUE}[2/5]${NC} Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install dependencies
echo ""
echo -e "${BLUE}[3/5]${NC} Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Setup API key
echo ""
echo -e "${BLUE}[4/5]${NC} Configuring Gemini API..."
if [ ! -f ".env" ]; then
    # Check if API key is provided as environment variable
    if [ -n "$GEMINI_API_KEY" ]; then
        echo "GEMINI_API_KEY=$GEMINI_API_KEY" > .env
        echo -e "${GREEN}✓${NC} API key configured from environment"
    else
        echo ""
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}Get your FREE Gemini API key:${NC}"
        echo -e "  ${BLUE}https://aistudio.google.com/apikey${NC}"
        echo -e ""
        echo -e "${YELLOW}Tip: Set GEMINI_API_KEY env var for non-interactive install${NC}"
        echo -e "  ${BLUE}export GEMINI_API_KEY=your_key_here${NC}"
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        read -p "$(echo -e ${GREEN}Enter your Gemini API key:${NC} )" API_KEY
        
        if [ -z "$API_KEY" ]; then
            echo -e "${RED}✗ API key cannot be empty${NC}"
            echo -e "${YELLOW}Run installer again with: export GEMINI_API_KEY=your_key${NC}"
            exit 1
        fi
        
        echo "GEMINI_API_KEY=$API_KEY" > .env
        echo -e "${GREEN}✓${NC} API key saved"
    fi
else
    echo -e "${GREEN}✓${NC} API key already configured"
fi

# Create launcher script
echo ""
echo -e "${BLUE}[5/5]${NC} Creating launcher..."
LAUNCHER="$HOME/.local/bin/shellsensei"
mkdir -p "$HOME/.local/bin"

cat > "$LAUNCHER" << 'LAUNCHER_SCRIPT'
#!/bin/bash
cd "$HOME/.shellsensei"
source venv/bin/activate
python3 tui_app.py "$@"
LAUNCHER_SCRIPT

chmod +x "$LAUNCHER"

# Add to PATH if needed
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo -e "${YELLOW}Adding ~/.local/bin to PATH...${NC}"
    
    SHELL_RC=""
    if [ -n "$BASH_VERSION" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -n "$ZSH_VERSION" ]; then
        SHELL_RC="$HOME/.zshrc"
    fi
    
    if [ -n "$SHELL_RC" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo -e "${GREEN}✓${NC} Added to $SHELL_RC"
        echo -e "${YELLOW}  Run: source $SHELL_RC${NC}"
    fi
fi

# Installation complete
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ ShellSensei installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}Run ShellSensei:${NC}"
echo -e "  ${GREEN}shellsensei${NC}"
echo ""
echo -e "${BLUE}Or directly:${NC}"
echo -e "  ${GREEN}$HOME/.local/bin/shellsensei${NC}"
echo ""
echo -e "${YELLOW}First time? The app will scan your system (takes ~30 seconds)${NC}"
echo ""
