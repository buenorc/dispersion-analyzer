# -*- coding: utf-8 -*-
"""Manual dos métodos (texto exibido em Ajuda → Métodos… na interface)."""

METODOS = """\
==============================================================================================
 MANUAL DOS MÉTODOS — DISPERSION ANALYZER
==============================================================================================

 O programa estima, a partir das curvas de passagem C(t) de um traçador (NaCl) medidas por
 condutivímetros, a velocidade média do escoamento U (m/s) e o coeficiente de dispersão
 longitudinal K (m²/s; na literatura também D ou D_L). Vários métodos são aplicados aos
 mesmos dados, para que os resultados possam ser comparados entre si.

 Sequência de cálculo
   1. leitura dos arquivos e conversão do tempo em "segundos desde o lançamento";
   2. pré-processamento de cada ponto (recorte, suavização, fundo do rio);
   3. conversão condutividade → concentração em excesso (calibração);
   4. delimitação da pluma, momentos temporais e descritores da curva;
   5. curva média de cada seção (quando há várias sondas na mesma seção);
   6. métodos de um ponto e métodos entre seções;
   7. hidráulica (flutuadores), vazão por diluição, fórmulas empíricas, mistura lateral.


----------------------------------------------------------------------------------------------
 1. NOTAÇÃO E HIPÓTESES GERAIS
----------------------------------------------------------------------------------------------
   x      distância do lançamento até a seção (m)
   t      tempo desde o lançamento (s)
   C      concentração de NaCl em excesso, acima do fundo do rio (kg/m³ = g/L)
   U      velocidade média do escoamento / da pluma (m/s)
   K      coeficiente de dispersão longitudinal (m²/s)
   M      massa de sal lançada (kg);   A = área da seção (m²);   Q = vazão (m³/s)

 Todos os métodos se apoiam na equação de advecção-dispersão unidimensional (ADE 1D):

        ∂C/∂t + U ∂C/∂x = K ∂²C/∂x²

 cuja solução para um lançamento instantâneo de massa M em x = 0, t = 0 é

        C(x,t) = (M/A) / √(4πKt) · exp[ −(x − Ut)² / (4Kt) ]

 Hipóteses (valem para TODOS os métodos; quando falham, os resultados se degradam):
   • lançamento instantâneo e pontual (o sal todo de uma vez);
   • traçador conservativo (não reage, não é absorvido, não infiltra);
   • escoamento permanente e trecho aproximadamente uniforme (U, K e Q constantes);
   • mistura completa na seção transversal (ver item 11: distância de mistura lateral);
   • sem zonas mortas importantes (remansos, poços), que produzem caudas longas.


----------------------------------------------------------------------------------------------
 2. DA CONDUTIVIDADE À CONCENTRAÇÃO
----------------------------------------------------------------------------------------------
 Concentração em excesso:   C(t) = f(EC(t)) − f(EC_fundo)
 onde f é a curva de calibração da sonda. Descontar f(EC_fundo) remove o sal que o rio já
 tem; por isso um desvio constante da sonda praticamente se cancela e o que importa é a
 inclinação da curva.

 Modos de calibração
   • Padrões de sal medidos com a sonda: polinômio de grau 1 a 3 ajustado por mínimos
     quadrados a (EC, C). A concentração pode ser digitada em g/L ou como nº de doses
     (colheres) de massa conhecida num volume conhecido.
   • Sonda × condutivímetro de referência (duas etapas): EC_ref = g(EC_sonda) por
     polinômio; em seguida C = f_ref(EC_ref), com a calibração do condutivímetro de
     referência. Os padrões só precisam ser medidos com o instrumento de referência.
   • NaCl teórico: condutividade molar tabelada do NaCl a 25 °C (CRC Handbook),
     interpolada; válida até ~10 700 µS/cm.
   • Fator fixo: C = fator · EC (padrão 0,0005 kg/m³ por µS/cm, isto é, 1 g/L ≈ 2000 µS/cm).

 Limitações
   • O programa NÃO faz compensação de temperatura (a coluna de temperatura é só lida).
     A sonda deve registrar a EC compensada para 25 °C, ou a calibração deve ser feita
     na mesma temperatura da água do rio. A EC varia cerca de 2 % por °C.
   • Fora da faixa dos padrões a curva é extrapolada (há aviso). Polinômios de grau 3
     extrapolam mal.
   • Se a curva não for monotônica na faixa medida há aviso: uma mesma EC corresponderia
     a duas concentrações.
   • Não copie coeficientes do rótulo da linha de tendência do Excel: ele arredonda para
     poucos algarismos (no L3, 2,2508E-06 virou 2E-06, cerca de 13 % de erro no pico).


----------------------------------------------------------------------------------------------
 3. PRÉ-PROCESSAMENTO (janela de cada ponto de monitoramento)
----------------------------------------------------------------------------------------------
 As etapas são aplicadas nesta ordem:

 a) Recorte dos dados (s): usa só o trecho [t_min, t_max]. Vazio = série inteira.

 b) Média móvel (amostras): média de N leituras consecutivas; 0 ou 1 = desligada.
    Limitação: janelas grandes achatam o pico e alargam a curva, aumentando σt² e K.
    Use N pequeno (3 a 5) e só quando o ruído for evidente.

 c) Fundo do rio (condutividade natural):
    auto    média das leituras ANTES da subida da curva (detectada automaticamente),
            afastando-se do "pé" da curva e descartando picos isolados (bolhas, ruído).
    window  média no intervalo de tempo informado.
    value   valor fixo informado (µS/cm, ou kg/m³ se o sinal já for concentração).
    linear  reta entre o fundo antes e o fundo depois da passagem (para deriva da sonda ou
            mudança de temperatura durante o ensaio). Se a curva não voltar ao fundo, usa
            fundo constante e avisa.
    Limitação: se o registro começa em cima da hora, há poucos dados antes da subida e o
    fundo automático fica incerto (há aviso) — use window ou value.

 d) Fim da pluma (fração do pico, padrão 0,02): a pluma termina quando C fica abaixo de
    2 % do pico por 3 leituras seguidas. Se isso nunca acontece, a série é "truncada".
    Um limiar maior corta a cauda mais cedo: massa, σt² e K diminuem.

 e) Zerar fora da pluma: C = 0 antes da subida e depois do fim da pluma; valores
    negativos também são zerados. Evita que o ruído do fundo entre nas integrais
    (principalmente em σt², que pondera os extremos pelo quadrado da distância ao centro).
    Recomendado deixar ligado.

 f) Extrapolar cauda truncada: se a série terminou antes de a pluma passar, ajusta uma
    exponencial C = C_fim · exp[−k(t − t_fim)] ao trecho de descida (C < 60 % do pico) e a
    prolonga até 0,1 % do pico. A fração da massa que veio da extrapolação aparece em
    "Cauda extrapolada (%)". A opção "Usar a cauda extrapolada nos cálculos" (aba Análise)
    decide se a cauda entra nos métodos.
    Limitação: a forma exponencial é uma hipótese. Se a extrapolação passar de ~10–20 %
    da massa, os resultados dependem mais da hipótese do que da medição.


----------------------------------------------------------------------------------------------
 4. MOMENTOS TEMPORAIS E DESCRITORES DA CURVA
----------------------------------------------------------------------------------------------
 Integrais pela regra do trapézio (aceita passo de tempo irregular):

   M0   = ∫ C dt                          (kg·s/m³)   "área" da curva
   <t>  = ∫ t·C dt / M0                   (s)         tempo médio de passagem (centroide)
   σt²  = ∫ (t − <t>)²·C dt / M0          (s²)        variância temporal
   σt   = √σt²                            (s)         desvio padrão temporal
   assimetria = [∫ (t − <t>)³·C dt / M0] / σt³        0 = simétrica; > 0 = cauda longa

   t_pico, C_pico   instante e valor do máximo
   chegada 10 %     primeiro instante com C ≥ 10 % do pico

 Limitação: σt² é muito sensível às caudas. Uma cauda cortada (série truncada) reduz σt²;
 ruído não removido na cauda aumenta σt². Por isso os itens 3d–3f importam.


----------------------------------------------------------------------------------------------
 5. MÉTODOS DE UM ÚNICO PONTO
----------------------------------------------------------------------------------------------
 Usam a curva de uma sonda (ou a curva média da seção) e a distância x ao lançamento.
 Exigem conhecer o INSTANTE DO LANÇAMENTO e x > 0; sem isso não são aplicados.
 Por padrão são aplicados a cada ponto e também à média de cada seção com várias sondas
 (opção "Analisar cada ponto individualmente").

 5.1 Velocidade do pico  —  U = x / t_pico   (só U)
     Limitação: a curva é assimétrica, e o pico chega antes do centroide. Perto do
     lançamento U fica superestimado (+18 % com Pe = 6; +3 % com Pe = 31; ver item 13).
     Também depende do intervalo de amostragem.

 5.2 Método dos momentos em um ponto ("nuvem congelada")
        U = x / <t>          K = U²·σt² / (2·<t>)
     A variância no tempo é convertida em variância no espaço (σx² = U²·σt²), supondo
     que a nuvem não muda de forma enquanto passa pela sonda; depois σx² = 2·K·t.
     Limitações:
       • só vale longe do lançamento. Com Pe = U·x/K baixo, U e K saem SUBESTIMADOS
         (Pe = 6: U −24 %, K −29 %; Pe = 31: U −6 %, K −6 %; Pe = 125: ~ −2 %);
       • muito sensível às caudas (via σt²).

 5.3 Método dos percentis em um ponto
        σt = (t84 − t16)/2      U = x / t50      K = U²·σt² / (2·t50)
     t16, t50 e t84 são os instantes em que passaram 15,87 %, 50 % e 84,13 % da massa
     (percentis da integral acumulada de C). É a forma correta da ideia "σ = 34 % de cada
     lado", usada no L3 (a planilha usava 1,34·C_pico, que tem unidade de concentração e
     não de tempo).
     Limitação: supõe curva aproximadamente gaussiana no tempo. É menos sensível às caudas
     que os momentos, mas tem o mesmo viés com Pe baixo, um pouco menor (Pe = 6: K −15 %).

 5.4 Método do ajuste da ADE
     Ajusta a solução analítica C(x,t) (item 1) aos dados por mínimos quadrados não
     lineares (Levenberg–Marquardt), com três parâmetros livres: U, K e M/A. Os
     parâmetros são otimizados em escala logarítmica (ficam sempre positivos); os chutes
     iniciais vêm do método dos momentos, e testam-se 3 valores iniciais de K
     (×1, ×0,2 e ×5), ficando o de menor erro.
     Qualidade: R², NSE e RMSE entre a curva observada e a ajustada (item 12).
     Limitações:
       • supõe a ADE ideal. Caudas longas (zonas mortas, remansos) não podem ser
         representadas: o ajuste "compensa" alterando U e K, e o NSE cai;
       • depende do instante do lançamento: um erro de relógio desloca a curva e muda U;
       • M/A é livre, portanto o ajuste NÃO verifica a conservação da massa.

 5.5 Método de Chatwin (1971)
     Linearização da solução da ADE:
        Y(t) = ±√[ t·ln( k / (C·√t) ) ] = x/(2√K) − U·t/(2√K),    k = (M/A)/√(4πK)
     Os pontos (t, Y) formam uma reta Y = b + a·t, de onde
        √K = x/(2b)        U = −a·x/b
     Como k depende de K, o cálculo é iterado até U e K convergirem (tolerância 10⁻⁶).
     O sinal de Y é negativo no ramo descendente (t > x/U).
     Opções e variantes
       • "Chatwin: usar C > …× C pico" (padrão 0,10): só entram pontos acima dessa fração
         do pico, porque a cauda ruidosa distorce a reta.
       • "M/A da curva medida": M/A = U·∫C dt (coerente com os próprios dados).
       • "M/A = massa lançada / área informada": M/A a partir da massa do projeto e da área
         da seção. Só é calculado quando ambas são informadas.
     Limitações:
       • mesmas hipóteses da ADE ideal (caudas longas curvam a "reta");
       • falha quando ln(...) < 0 (k pequeno demais) ou quando a reta não tem sentido
         físico (b ≤ 0 ou a ≥ 0) — há aviso e o método é omitido;
       • se as duas variantes de M/A diferirem muito, a massa não se conservou ou a área
         está errada.


----------------------------------------------------------------------------------------------
 6. MÉTODOS ENTRE DUAS SEÇÕES
----------------------------------------------------------------------------------------------
 Usam as curvas de duas seções (a curva média, quando há várias sondas) em x1 < x2.
 NÃO dependem do instante do lançamento nem da distância até ele — só de Δx = x2 − x1.
 "Pares de seções": consecutivas (A→B, B→C) ou todas as combinações (A→B, A→C, B→C).

 6.1 Método de Fischer (variação dos momentos; Fischer, 1968)
        U = Δx / Δ<t>          K = U²·(σt2² − σt1²) / (2·Δ<t>)
     O termo de "nuvem congelada" se cancela na diferença; com a ADE ideal o resultado é
     exato mesmo perto do lançamento.
     Limitações:
       • exige Δσt² > 0 (a curva de jusante tem de ser mais larga). Se não for, K não tem
         sentido físico (há aviso): curva truncada, mistura incompleta ou calibração ruim;
       • MUITO sensível a caudas cortadas. Exemplo com a ADE ideal (x = 10 → 30 m): cortar
         a curva de jusante em 1,4·<t> muda U de 0,25 para 0,29 m/s e K de 0,40 para
         0,06 m²/s. Use a extrapolação de cauda e registre até a pluma passar;
       • as duas seções devem estar além da distância de mistura lateral (item 11).

 6.2 Método da propagação ("routing"; Fischer, 1968)
     A curva medida em x1 é propagada até x2 pela ADE e comparada com a curva medida em x2:
        C(x2,t) = ∫ C(x1,τ) · U/√(4πK·Δt̄) · exp{ −[U·(Δt̄ − t + τ)]² / (4K·Δt̄) } dτ
     com Δt̄ = <t>2 − <t>1 (dos momentos). K é o valor que minimiza a soma dos quadrados
     entre a curva propagada e a observada (busca em escala log, entre 10⁻⁵ e 50 m²/s).
     Por padrão U = Δx/Δt̄ fica fixo.
     Opções
       • Otimizar também U: U e K livres (Nelder–Mead, 5 pontos de partida).
       • Normalizar a massa: multiplica a curva de montante por M0(x2)/M0(x1), de modo
         que se comparam só as FORMAS das curvas. Útil quando a massa não se conservou
         (calibrações diferentes entre sondas, perdas).
       • Avaliar também K e U manuais: calcula a curva propagada e o erro com valores
         digitados, sem otimizar — equivale à tentativa e erro da planilha L3. U vazio =
         Δx/Δt̄.
     Resultados: K, U, R², NSE, RMSE e a curva de sensibilidade RMSE × K (figura
     "Convergência"). Um mínimo bem marcado indica K bem determinado; uma curva achatada
     indica que vários K explicam os dados igualmente.
     Limitações:
       • usa a curva INTEIRA, por isso é menos sensível às caudas que o método de Fischer,
         mas ainda supõe U e K constantes entre as seções;
       • sem normalizar, uma diferença de massa entre as seções (∫C dt diferente) é
         "absorvida" por K;
       • a curva de montante é truncada/reamostrada internamente para acelerar o cálculo
         (sem efeito prático quando a amostragem é densa).


----------------------------------------------------------------------------------------------
 7. VÁRIAS SONDAS NA MESMA SEÇÃO: CURVA MÉDIA E MISTURA LATERAL
----------------------------------------------------------------------------------------------
 A curva da seção é a média ponderada das curvas das sondas, numa grade de tempo comum:
        C_seção(t) = Σ wi·Ci(t) / Σ wi        (wi = "Peso na média" de cada ponto)
 Use como peso a subárea ou a vazão parcial que cada sonda representa (iguais = média
 simples). Fora do período registrado por uma sonda, ela não entra na média.

 Tabela "Mistura lateral" (para cada seção com 2 ou mais sondas):
   • CV da integral da concentração = desvio padrão / média de M0 entre as sondas;
   • desvio máximo da integral e diferença do tempo médio de passagem entre as sondas;
   • CV ≤ 10 % → mistura completa;  CV > 10 % → incompleta (há aviso).
 Limitação: com mistura incompleta, a curva média e a vazão por diluição dependem dos
 pesos escolhidos.


----------------------------------------------------------------------------------------------
 8. MASSA, VAZÃO POR DILUIÇÃO E RECUPERAÇÃO
----------------------------------------------------------------------------------------------
   Vazão pelo traçador (diluição):   Q_dil = M / ∫C dt          (exige a massa lançada)
   Massa recuperada:                 M_rec = Q · ∫C dt          (exige Q da seção)
   Recuperação:                      M_rec / M × 100 %

 Com Q constante, ∫C dt deve ser IGUAL em todas as seções (figura "Conservação de massa";
 tabela de pares: razão ∫C dt 2/1). Diferenças acima de 15 % geram aviso.
 Limitações: exigem mistura completa, traçador conservativo e vazão constante no trecho.
 Recuperação muito diferente de 100 % indica erro de calibração, fundo, curva truncada,
 mistura incompleta, massa lançada imprecisa ou Q dos flutuadores errado.


----------------------------------------------------------------------------------------------
 9. HIDRÁULICA DA SEÇÃO (aba Seções)
----------------------------------------------------------------------------------------------
   Área:                    A = área informada, ou largura × profundidade
   Velocidade superficial:  Vs = média de (distância / tempo) dos flutuadores
   Velocidade média:        V = coef · Vs   (coeficiente do projeto, padrão 0,85)
                            ou a V conhecida, se informada
   Vazão:                   Q = V · A,  ou a Q conhecida, se informada
   Raio hidráulico:         R = A / (largura + 2·profundidade)
   Velocidade de atrito:    u* = √(g·R·S), com S = declividade do projeto
                            (sem declividade: u* ≈ 0,1·U, estimativa grosseira)

 Limitações: o coeficiente 0,85 é típico (0,8–0,9), mas depende da rugosidade e da
 profundidade. Flutuadores em trecho curto ou com vento dão Vs pouco confiável.
 u* estimado como 0,1·U pode errar por um fator 2 ou mais.

 U (traçador) × V (flutuadores): num trecho uniforme e bem misturado devem ser parecidos.
 U bem menor que V sugere zonas mortas que retêm o traçador; diferenças grandes também
 podem vir do coeficiente dos flutuadores ou de uma seção pouco representativa.


----------------------------------------------------------------------------------------------
 10. FÓRMULAS EMPÍRICAS DE K
----------------------------------------------------------------------------------------------
 Com W = largura, h = profundidade, U = V da seção (ou, sem V, o U de Fischer) e u*:
   Elder (1959)                    K = 5,93·h·u*
   Fischer (1975)                  K = 0,011·U²·W² / (h·u*)
   Liu (1977)                      K = 0,18·(u*/U)^1,5 · U²·W² / (h·u*)
   Seo & Cheong (1998)             K = 5,915·(W/h)^0,620 · (U/u*)^1,428 · h·u*
   Kashefipour & Falconer (2002)   K = 10,612·h·U² / u*

 Limitações: são estimativas de ORDEM DE GRANDEZA, calibradas em rios maiores. Erros por
 um fator de 2 a 10 são comuns, e as fórmulas divergem muito entre si. Elder (canal
 largo e infinito, só cisalhamento vertical) costuma subestimar K em rios naturais.
 Servem para verificar se o K medido está numa faixa plausível — não substituem a medição.


----------------------------------------------------------------------------------------------
 11. DISTÂNCIA DE MISTURA LATERAL ("Zona de Taylor?")
----------------------------------------------------------------------------------------------
   Mistura transversal:   ε_t = 0,6·h·u*                      (Fischer et al., 1979)
   Lançamento no centro:  L = 0,1·U·W² / ε_t
   Lançamento na margem:  L = 0,4·U·W² / ε_t    (4 vezes mais longe)

 Se x ≥ L, a seção está na zona em que a ADE 1D vale ("sim"). Se x < L, o sal ainda não
 ocupa a largura toda e K pode sair errado (há aviso).
 Limitação: ε_t e L têm incerteza grande (fator ~2), sobretudo se u* foi estimado.
 Use como indicação, junto com o CV entre sondas da mesma seção (item 7).


----------------------------------------------------------------------------------------------
 12. INDICADORES DE QUALIDADE DOS AJUSTES
----------------------------------------------------------------------------------------------
   RMSE = √[ média (C_obs − C_calc)² ]                       mesma unidade de C
   NSE  = 1 − Σ(C_obs − C_calc)² / Σ(C_obs − média C_obs)²   1 = perfeito; < 0 = pior
                                                             que usar a média
   R²   = (correlação entre C_obs e C_calc)²   (no Chatwin: R² da reta Y × t)

 O R² mede só a correlação (a forma), não o viés; o NSE penaliza também diferenças de
 nível e de posição. Prefira o NSE para julgar os ajustes da ADE e da propagação.


----------------------------------------------------------------------------------------------
 13. COMO INTERPRETAR E ESCOLHER
----------------------------------------------------------------------------------------------
 Número de Péclet:  Pe = U·x / K  (x = distância do lançamento).
 Teste com a ADE ideal (U = 0,25 m/s, K = 0,40 m²/s, sem ruído):

      Pe   | momentos 1 ponto | percentis 1 ponto | pico  | ADE / Chatwin / Fischer
      -----+------------------+-------------------+-------+-------------------------
       6   |  U −24 %  K −29 % |  U −14 %  K −15 % | +18 % |  exatos
      31   |  U −6 %   K −6 %  |  U −3 %   K −3 %  |  +3 % |  exatos
     125   |  U −2 %   K −2 %  |  U −1 %   K −1 %  |  +1 % |  exatos

 Recomendações
   • Métodos entre seções (Fischer e propagação) são os mais confiáveis: não dependem do
     instante do lançamento nem da hipótese de nuvem congelada. A propagação é a mais
     robusta a caudas.
   • Entre os de um ponto, prefira o ajuste da ADE e o Chatwin; use momentos e percentis
     como verificação, lembrando do viés com Pe baixo.
   • Resultados coerentes entre métodos diferentes aumentam a confiança. Divergências
     grandes costumam apontar: curva truncada, mistura lateral incompleta, calibração,
     fundo mal estimado, relógio do datalogger ou caudas longas (zonas mortas).
   • Leia sempre os AVISOS do relatório: eles indicam qual hipótese pode ter falhado.
   • Planejamento de campo: seções bem além da distância de mistura lateral, registro até a
     condutividade voltar ao fundo e relógios sincronizados (ou "Correção do relógio").


----------------------------------------------------------------------------------------------
 REFERÊNCIAS
----------------------------------------------------------------------------------------------
   Chatwin, P. C. (1971). On the interpretation of some longitudinal dispersion
     experiments. Journal of Fluid Mechanics, 48(4), 689–702.
   Elder, J. W. (1959). The dispersion of marked fluid in turbulent shear flow.
     Journal of Fluid Mechanics, 5(4), 544–560.
   Fischer, H. B. (1968). Methods for predicting dispersion coefficients in natural streams,
     with applications to lower reaches of the Green and Duwamish Rivers, Washington.
     USGS Professional Paper 582-A.
   Fischer, H. B. (1975). Discussion of "Simple method for predicting dispersion in
     streams". Journal of the Environmental Engineering Division, ASCE, 101(3), 453–455.
   Fischer, H. B.; List, E. J.; Koh, R. C. Y.; Imberger, J.; Brooks, N. H. (1979). Mixing in
     Inland and Coastal Waters. Academic Press.
   Kashefipour, S. M.; Falconer, R. A. (2002). Longitudinal dispersion coefficients in
     natural channels. Water Research, 36(6), 1596–1608.
   Liu, H. (1977). Predicting dispersion coefficient of streams. Journal of the
     Environmental Engineering Division, ASCE, 103(1), 59–69.
   Seo, I. W.; Cheong, T. S. (1998). Predicting longitudinal dispersion coefficient in
     natural streams. Journal of Hydraulic Engineering, 124(1), 25–32.
"""
