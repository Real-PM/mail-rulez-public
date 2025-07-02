# Mail-Rulez

[![License: Dual AGPL v3 / Commercial](https://img.shields.io/badge/License-Dual%20AGPL%20v3%20%2F%20Commercial-blue.svg)](LICENSE-DUAL)
[![Docker Pulls](https://img.shields.io/docker/pulls/realpm/mail-rulez)](https://github.com/orgs/Real-PM/packages)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/Real-PM/mail-rulez-public/releases)

**Mail-Rulez** is an intelligent IMAP email management system that automates inbox processing through sophisticated rules-based filtering and list management.

## 🚀 Quick Start

```bash
# Pull and run with Docker
docker run -d \
  --name mail-rulez \
  -p 5001:5001 \
  -v mail_rulez_data:/app/data \
  ghcr.io/real-pm/mail-rulez:latest

# Or use Docker Compose
curl -O https://raw.githubusercontent.com/Real-PM/mail-rulez-public/main/docker/docker-compose.yml
docker-compose up -d
```

Access the web interface at `http://localhost:5001`

## 🎯 Key Features

- **Smart Email Processing**: Automated rules-based filtering with whitelist/blacklist/vendor lists
- **Multi-Account Support**: Manage multiple IMAP accounts from one interface  
- **Visual Rule Builder**: Create complex email workflows without coding
- **Startup & Maintenance Modes**: Handle email backlogs or ongoing processing
- **Docker Ready**: One-command deployment with automatic configuration
- **Privacy First**: Self-hosted solution keeps your data under your control

## 📋 Installation

### Requirements
- Docker 20.10+ or Python 3.9+
- 512MB RAM minimum
- IMAP access to email accounts

### Docker Installation (Recommended)
```bash
# Using Docker Compose
wget https://raw.githubusercontent.com/Real-PM/mail-rulez-public/main/docker/docker-compose.yml
docker-compose up -d
```

### Manual Installation
```bash
# Clone repository
git clone https://github.com/Real-PM/mail-rulez-public.git
cd mail-rulez

# Install dependencies
pip install -r requirements.txt

# Run application
python web/app.py
```

## ⚙️ Configuration

1. Access web interface at `http://localhost:5001`
2. Default login: `admin` / `changeme`
3. Add IMAP accounts through the interface
4. Create processing rules and lists
5. Choose startup or maintenance mode

## 📄 License

Mail-Rulez is dual-licensed:
- **AGPL v3** for open source/self-hosted use
- **Commercial License** for hosted services - contact license@mail-rulez.com

See [LICENSE-DUAL](LICENSE-DUAL) for details.

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Configuration Guide](docs/configuration.md)  
- [Deployment Guide](docs/deployment.md)
- [API Reference](docs/api-reference.md)

## 🆘 Support

- **Documentation**: https://github.com/Real-PM/mail-rulez-public/wiki
- **Issues**: https://github.com/Real-PM/mail-rulez-public/issues
- **Commercial Support**: support@mail-rulez.com

---

**Mail-Rulez** - Intelligent Email Management Made Simple

Copyright (c) 2024 Real Project Management Solutions
