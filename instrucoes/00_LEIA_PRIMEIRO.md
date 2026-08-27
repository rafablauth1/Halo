# Leia primeiro

Todas as instruções do projeto **CISPR15 Toolkit** foram reunidas nesta
pasta única (`instrucoes/`), em vez de espalhadas nos comentários do
código. Leia nesta ordem:

1. **01_instalacao_e_uso.md** — como instalar e rodar o programa, e
   como usar a tela principal.
2. **02_pendencias_limites_de_norma.md** — as cinco tabelas de limite da
   norma (itens 4.3.1 a 4.4.2), já preenchidas, e o que ainda não está
   coberto (incertezas, cláusula 5, perdas de inserção).
3. **03_validacao_receiver_scpi.md** — passo a passo para testar e
   validar o controle remoto do receiver R&S no seu laboratório
   (aquisição ao vivo, ainda não testada contra hardware real).
4. **04_lisn_e_fatores_de_correcao.md** — o que fazer com a LISN
   (ENV216/ESH2-Z5) e os fatores de correção (cabo, antena).
5. **05_arquitetura_e_como_estender.md** — como o código é organizado
   e como adicionar uma norma nova (ou completar as 3 já existentes:
   conduzida, loop, radiada).
6. **06_normas_e_correcoes_configuraveis.md** — como criar/editar/
   excluir normas e tabelas de correção direto pela tela, sem editar
   JSON na mão (gerenciadores estilo RadiMation).
7. **07_receiver_gpib_e_configuracoes.md** — catálogo de receivers R&S
   pré-setados (cada um com seus comandos SCPI), conexão GPIB/VISA e
   todas as configurações de receiver exigidas pela norma.
8. **08_equipamentos_e_certificados.md** — cadastro de cabos, LISNs e
   antenas com certificado de calibração, e a correção do erro
   sistemático aplicada interpolada ao ensaio.
9. **09_conferencia_config_lab.md** — a configuração real do
   RadiMation do laboratório conferida contra a CISPR 15, e o que divergiu.

Resumo de uma frase por arquivo, se você só quiser abrir um:

- Quer só rodar o programa? → `01_instalacao_e_uso.md`
- Quer ver as tabelas de limite da norma que estão no software? → `02_pendencias_limites_de_norma.md`
- Vai testar com o receiver R&S de verdade? → `03_validacao_receiver_scpi.md`
- Vai usar a LISN/antena loop reais? → `04_lisn_e_fatores_de_correcao.md`
- Quer mexer no código / adicionar outra norma? → `05_arquitetura_e_como_estender.md`
- Quer criar/editar suas próprias normas e tabelas de correção pela tela? → `06_normas_e_correcoes_configuraveis.md`
- Vai configurar o receiver R&S via GPIB e os parâmetros de norma? → `07_receiver_gpib_e_configuracoes.md`
- Vai cadastrar cabo/LISN/antena e aplicar o certificado de calibração? → `08_equipamentos_e_certificados.md`
- Quer saber o que divergiu entre o RadiMation do laboratório e a norma? → `09_conferencia_config_lab.md`
