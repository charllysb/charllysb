# Publicando na Google Play

## Modelo de monetização (decidido)

- **Grátis:** 4 salvamentos por dia (MP3 incluso).
- **Pro:** ilimitado para sempre, compra única de **R$ 9,90** (produto in-app no Play Console).
- Contagem local no aparelho; compra verificada pela Play Billing (`Billing.kt`).
- O limite fica em `DailyQuota.FREE_DAILY_LIMIT`; o ID do produto em `Billing.PRO_PRODUCT_ID` (`zapsaver_pro`).

## 1. Criar a chave de upload (uma vez só)

```bash
keytool -genkeypair -v -keystore upload.jks -alias upload \
  -keyalg RSA -keysize 4096 -validity 10000
```

Guarde `upload.jks` e as senhas num lugar seguro (gerenciador de senhas). **Nunca** commite esse arquivo. Com o Play App Signing, se perder essa chave dá pra pedir reset ao Google, mas é chato.

## 2. Gerar o AAB assinado

**Pelo GitHub Actions (recomendado):** em _Settings → Secrets and variables → Actions_, crie:

| Secret | Valor |
|---|---|
| `ZAPSAVER_KEYSTORE_BASE64` | saída de `base64 -w0 upload.jks` |
| `ZAPSAVER_KEYSTORE_PASSWORD` | senha do keystore |
| `ZAPSAVER_KEY_ALIAS` | `upload` |
| `ZAPSAVER_KEY_PASSWORD` | senha da chave |

O próximo push gera o artifact `zap-saver-release-aab`.

**Local:** crie `keystore.properties` na pasta do projeto (já está no `.gitignore`):

```properties
storeFile=upload.jks
storePassword=...
keyAlias=upload
keyPassword=...
```

e rode `./gradlew bundleRelease` → `app/build/outputs/bundle/release/app-release.aab`.

A cada nova versão, aumente `versionCode` (e `versionName`) em `app/build.gradle.kts`.

## 3. Play Console

1. Conta de desenvolvedor: taxa única de US$ 25 + verificação de identidade.
2. **Conta pessoal nova:** antes de liberar em produção, o Google exige um **teste fechado com pelo menos 12 testadores por 14 dias seguidos**. Comece isso cedo (amigos e família servem).
3. Criar app → nome, idioma padrão pt-BR, app gratuito.
4. Subir o AAB numa trilha de teste e ativar o **Play App Signing**.
5. **Produto Pro:** depois de subir o primeiro AAB (o Console só libera produtos para apps com a permissão de billing), vá em _Monetizar → Produtos → Produtos no app_ e crie:
   - ID do produto: `zapsaver_pro` (tem que ser exatamente esse)
   - Nome: Zap Saver Pro · Descrição: Salvamentos ilimitados para sempre
   - Preço: R$ 9,90 → **Ativar**
   - A compra só funciona no app instalado pela Play (trilha de teste). No APK do GitHub o botão avisa que não está disponível, e isso é esperado.
   - Para testar sem pagar: _Configurações → Teste de licença_, adicione seu Gmail. Aparecem cartões de teste na hora de comprar.
6. Preencher: política de privacidade (URL pública do `PRIVACY.md`, ex.: link do GitHub), classificação de conteúdo, público-alvo, **Segurança dos dados: "não coleta nem compartilha dados"**, anúncios: não.

## 4. Cuidado com a marca "WhatsApp"

A Play costuma recusar apps que usam marca de terceiros no nome ou no ícone. Por isso:

- Nome e ícone **não** usam "WhatsApp" nem o logo/verde exato dele.
- Na descrição, mencione o WhatsApp só de forma descritiva e deixe claro que não há vínculo (o texto abaixo já faz isso).
- O nome da pasta do projeto no repositório não importa para a loja.

## 5. Texto da página da loja

**Nome (até 30):** Zap Saver: salvar mídias

**Descrição curta (até 80):** Salve áudios, fotos e vídeos direto na pasta Download. Converte áudio para MP3.

**Descrição completa:**

> Cansou de procurar onde foi parar aquele áudio ou vídeo que te mandaram? Com o Zap Saver é só compartilhar e pronto: o arquivo vai direto para a pasta Download do seu celular.
>
> **Como funciona**
> 1. Segure a mídia na conversa e toque em Compartilhar.
> 2. Escolha "Salvar em Downloads" ou "Salvar como MP3".
> 3. Pronto! O arquivo aparece na pasta Download.
>
> **Recursos**
> • Salva fotos, vídeos, áudios e documentos com um toque
> • Converte mensagens de voz para MP3, que toca em qualquer lugar
> • Extrai o áudio de vídeos em MP3
> • Salva vários arquivos de uma vez
> • Sem anúncios, sem cadastro e sem acesso à internet: seus arquivos nunca saem do celular
>
> **Grátis e Pro**
> Use de graça com 4 salvamentos por dia. Precisa de mais? O Pro libera salvamentos ilimitados para sempre, com pagamento único e sem assinatura.
>
> Funciona com qualquer app que permita compartilhar arquivos, incluindo apps de mensagens como o WhatsApp.
>
> Zap Saver é um app independente e não tem nenhuma relação com o WhatsApp ou a Meta.

**Categoria:** Ferramentas

**Imagens necessárias:** ícone 512×512 (`store/icon-512.png`, gerado por `store/make_icon.py`), imagem de destaque 1024×500 e pelo menos 2 capturas de tela do celular.
