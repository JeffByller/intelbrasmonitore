# Intelbras Monitore - Coletor de Metricas OLT e MikroTik

Sistema web para monitoramento, coleta automatizada de metricas e auditoria de equipamentos OLT Intelbras e roteadores MikroTik RouterOS, com envio de alertas para o Telegram, retencao inteligente de dados e dashboard em tempo real.

---

## Funcionalidades

- Monitoramento de OLTs Intelbras:
  - Coleta de status de portas PON, contagem de ONUs ativas e inativas.
  - Extracao de niveis de potencia optica (RX/TX).
  - Identificacao e listagem detalhada de ONUs com status operacional.
  - Historico de metricas e desempenho de placas/slots.

- Monitoramento de Roteadores MikroTik (RouterOS):
  - Metricas de desempenho: uso de CPU, memoria, consumo de disco e uptime.
  - Trafego em tempo real por interface.
  - Monitoramento de sessoes BGP e estado dos peers.
  - Monitoramento de status RADIUS e clientes bloqueados.
  - Identificacao dos maiores consumidores de trafego (Top Clients).

- Sistema de Alertas via Telegram:
  - Notificacoes instantaneas em caso de falhas de comunicacao ou anomalias.
  - Alertas configuraveis para eventos de rede e quedas de conexao.

- Seguranca e Gerenciamento de Credenciais:
  - Criptografia simetrica (AES/Fernet) para credenciais de acesso aos equipamentos armazenadas no banco de dados.
  - Painel administrativo autenticado via JWT e cookies de sessao protegidos.
  - Isolamento de segredos atraves de variaveis de ambiente (.env).

- Retencao e Otimizacao Automatizada:
  - Execucao de tarefas em segundo plano gerenciadas via APScheduler.
  - Rotina automatica de purga para metricas antigas (retencao padrao limitada a 30 dias), evitando sobrecarga de disco e memoria.

---

## Tecnologias Utilizadas

- Backend: Python 3 (FastAPI, Uvicorn, SQLAlchemy 2.0 Async, APScheduler, Paramiko, Passlib/BCrypt, Cryptography)
- Frontend: Templates Jinja2 com interface responsiva e componentes interativos
- Banco de Dados: PostgreSQL 15 (com driver assincrono asyncpg)
- Infraestrutura: Docker e Docker Compose com controle de limites de memoria e CPU

---

## Estrutura do Projeto

- app/
  - collectors/: Scripts de conexao e extracao de metricas (OLT e MikroTik via SSH/API).
  - services/: Servicos auxiliares, incluindo integracao com Telegram.
  - static/: Arquivos estaticos (CSS, JS, imagens).
  - templates/: Telas e visualizacoes Jinja2 do painel web.
  - config.py: Configuracoes gerais e leitura de variaveis de ambiente.
  - crypto.py: Utilitarios de criptografia e decriptografia de credenciais (Fernet).
  - database.py: Modelos de dados SQLAlchemy e inicializacao do PostgreSQL.
  - main.py: Rotas FastAPI, autenticacao e endpoints do sistema.
  - scheduler.py: Agendador de tarefas periodicas de coleta e retencao.
- docker-compose.yml: Orquestracao dos servicos da aplicacao e do banco PostgreSQL.
- Dockerfile: Imagem conteinerizada da aplicacao FastAPI.
- .env.example: Modelo de configuracao das variaveis de ambiente.

---

## Pre-requisitos

- Docker Engine (versao 20.10 ou superior)
- Docker Compose (v2 ou plugin docker compose)

---

## Instalacao e Execucao

1. Clone o repositorio:
```bash
git clone git@github.com:JeffByller/intelbrasmonitore.git
cd intelbrasmonitore
```

2. Crie o arquivo de variaveis de ambiente a partir do modelo:
```bash
cp .env.example .env
```

3. Configure o arquivo `.env` com suas senhas e parametros de seguranca:
- `POSTGRES_USER`: Usuario do PostgreSQL (ex: monitor_user).
- `POSTGRES_PASSWORD`: Senha segura para o banco de dados.
- `POSTGRES_DB`: Nome do banco de dados (ex: monitor_db).
- `DATABASE_URL`: String de conexao assincrona (`postgresql+asyncpg://monitor_user:SUA_SENHA@db:5432/monitor_db`).
- `ADMIN_PASSWORD`: Senha mestra de acesso ao painel web.
- `SECRET_KEY`: Chave secreta aleatoria e longa para geracao dos tokens JWT e derivacao de chaves criptograficas.
- `PORT`: Porta HTTP exposta para o host (padrao: 8085).
- `TZ`: Fuso horario do sistema (ex: America/Recife).

4. Inicie os containers com o Docker Compose:
```bash
docker compose up -d --build
```

5. Verifique o status dos containers:
```bash
docker compose ps
docker compose logs -f app
```

6. Acesse a interface web:
Abra seu navegador em:
```
http://localhost:8085
```
(ou substitua pelo IP do servidor e porta definidos no arquivo `.env`).

---

## Configuracao de Equipamentos e Alertas

Apos logar no painel administrativo:
1. Acesse as configuracoes para cadastrar os IPs, portas e credenciais de acesso aos equipamentos OLT Intelbras e MikroTik. As senhas serao automaticamente criptografadas antes de serem salvas no PostgreSQL.
2. Defina os intervalos de coleta desejados para os jobs agendados.
3. Configure o Token do bot e o Chat ID do Telegram para ativacao das notificacoes de alertas.

---

## Politica de Retencao de Dados

Para garantir alta performance e evitar consumo excessivo de espaco em disco, o sistema executa automaticamente uma rotina de limpeza noturna. Os registros de metricas historicas de OLT e MikroTik sao retidos por ate 30 dias.
