# 🌐 JNET - Monitoramento OLT Intelbras 8820 & MikroTik Concentrador

Sistema de telemetria, diagnóstico e monitoramento em tempo real desenvolvido para Provedores de Internet (ISPs). O sistema realiza a coleta automatizada de métricas de OLTs **Intelbras 8820** e concentradores **MikroTik RouterOS**, com alertas automatizados via **Telegram** e interface web moderna estilo *Glassmorphism*.

---

## 🚀 Principais Funcionalidades

### 📡 1. OLT Intelbras 8820 (GPON)
* **Status em Tempo Real:** Leitura de ONUs Online/Offline, consumo de CPU/Memória da OLT e versão do Firmware.
* **Diagnóstico de Transceivers PON:** Monitoramento das 8 portas PON GBIC (Potência Tx, Rx e Temperatura).
* **Nível de Sinal Óptico:** Leitura e média de sinal Rx de todas as ONUs conectadas.
* **Tabela de ONUs Paginada:**
  * Busca instantânea por Nome, Serial MAC, GPON (Slot/Porta/ID) e Modelo.
  * Filtros rápidos para **Online**, **Offline** e **Sinal Baixo (<-25 dBm)**.
  * Identificação automática de fabricantes (Intelbras, Huawei, ZTE, V-SOL, FiberHome, TP-Link).

### 🌐 2. Concentrador MikroTik RouterOS
* **Sessões PPPoE:** Contagem e histórico de conexões ativas.
* **Desempenho:** Monitoramento de uso de CPU, RAM Livre, Uptime e Modelo da RouterBoard.
* **Sessões BGP (Core):** Acompanhamento do estado das sessões BGP (Established, Active, Idle) com alerta automático de queda/restabelecimento.
* **Servidores RADIUS:** Status de conectividade e contagem de requisições Aceitas / Rejeitadas.
* **Clientes Bloqueados:** Tabela dedicada para exibição de clientes na lista `rbfull_pgcorte`.
* **Top 10 Conexões:** Lista dos clientes PPPoE conectados há mais tempo.
* **Interfaces Ethernet:** Status das portas de rede (Link Up/Down, velocidade e comentários).

### 📈 3. Gráficos de Histórico & Alertas
* **Gráficos em Tempo Real:** Histórico de ONUs e conexões PPPoE com renderização fluida via Chart.js (escala calibrada em base zero para precisão de variações).
* **Bot do Telegram:** Notificação automática em caso de queda de sessão BGP ou variações bruscas de clientes PPPoE ativas.
* **Painel de Configuração Web:** Modal para ajustar IPs, credenciais SSH/API e parâmetros de rotina diretamente no navegador.

---

## 🛠️ Tecnologias Utilizadas

### Backend
* **Python 3.11+ / FastAPI**
* **AsyncIO / AsyncSSH** (para comunicação de alta performance via CLI com a OLT)
* **RouterOS API** (integração direta com o MikroTik)
* **APScheduler** (agendador de tarefas em segundo plano)
* **SQLAlchemy Async / AsyncPG**

### Frontend
* **HTML5 / Vanilla CSS3** (Design Glassmorphism com suporte a Dark Mode)
* **JavaScript ES6+**
* **Chart.js** (gráficos interativos)
* **FontAwesome 6** (ícones de rede e infraestrutura)

### Infraestrutura
* **Docker & Docker Compose**
* **PostgreSQL 15 (Alpine)**

---

## 📦 Como Executar o Projeto

### Pré-requisitos
* Docker instalado (`docker --version`)
* Docker Compose instalado (`docker compose version`)

### 1. Clonar o Repositório
```bash
git clone https://github.com/JeffByller/intelbrasmonitore.git
cd intelbrasmonitore
```

### 2. Iniciar os Contêineres
Execute o comando abaixo para subir o banco de dados PostgreSQL e a aplicação web:

```bash
docker compose up -d --build
```

### 3. Acessar a Aplicação
Abra o navegador e acesse:
```
http://localhost:8085
```

> **Credenciais Padrão de Acesso:**  
> * **Senha de Admin:** `suasenhaqui` (pode ser alterada via variáveis de ambiente no `docker-compose.yml`)

---

## 📂 Estrutura do Repositório

```text
intelbrasmonitore/
├── app/
│   ├── collectors/       # Módulos de coleta CLI (OLT Intelbras) e RouterOS API (MikroTik)
│   ├── services/         # Serviços de envio de alertas (Telegram, etc.)
│   ├── static/           # Estilos CSS, scripts JavaScript e imagens da interface
│   ├── templates/        # Páginas HTML (Login, Dashboard)
│   ├── config.py         # Configurações globais e variáveis de ambiente
│   ├── database.py       # Modelos SQLAlchemy e inicialização do banco
│   ├── scheduler.py      # Agendador de rotinas periódicas de coleta
│   └── main.py           # Aplicação principal FastAPI e endpoints da API
├── docker-compose.yml    # Orquestração dos serviços App e PostgreSQL
├── Dockerfile            # Containerização da aplicação Python
├── requirements.txt      # Dependências do projeto
└── .gitignore            # Arquivos ignorados pelo repositório Git
```

---

## 📄 Licença

Este projeto foi desenvolvido para uso em monitoramento de infraestrutura de telecomunicações do provedor **JNET Telecomunicações**.
