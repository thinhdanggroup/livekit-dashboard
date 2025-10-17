#!/bin/bash
# LiveKit Dashboard Setup Script

set -e

echo "🚀 LiveKit Dashboard Setup Script"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo -e "${RED}Error: Python 3.10 or higher is required. Found: $python_version${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $python_version${NC}"
echo ""

# Check if Poetry is installed
echo -e "${BLUE}Checking Poetry installation...${NC}"
if ! command -v poetry &> /dev/null; then
    echo -e "${YELLOW}Poetry not found. Installing Poetry...${NC}"
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
else
    echo -e "${GREEN}✓ Poetry is installed${NC}"
fi
echo ""

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
poetry install
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${BLUE}Creating .env file...${NC}"
    cat > .env << EOF
# LiveKit Server Configuration
LIVEKIT_URL=http://localhost:7880
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Admin Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# Application Settings
APP_SECRET_KEY=$(openssl rand -hex 32)
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Feature Flags
ENABLE_SIP=false
EOF
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}⚠️  Please edit .env with your LiveKit credentials${NC}"
else
    echo -e "${YELLOW}.env file already exists${NC}"
fi
echo ""

# Summary
echo -e "${GREEN}=================================="
echo "✓ Setup complete!"
echo "==================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Edit .env with your LiveKit server credentials"
echo "2. Run the dashboard:"
echo "   ${GREEN}make dev${NC}    # Development mode with auto-reload"
echo "   ${GREEN}make run${NC}    # Production mode"
echo ""
echo "3. Access the dashboard at: ${GREEN}http://localhost:8000${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  ${GREEN}make help${NC}   # Show all available commands"
echo "  ${GREEN}make test${NC}   # Run tests"
echo "  ${GREEN}make lint${NC}   # Run linters"
echo ""
echo -e "${YELLOW}Need help? Check the README.md or open an issue on GitHub${NC}"
echo ""

