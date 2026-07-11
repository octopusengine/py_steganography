# Steganogra

Dokumentace k programu pro vizuální kryptografii a steganografii. Program vytváří dvě samostatné vrstvy, které po vytištění nebo digitálním překrytí odhalí skrytý text nebo obraz.

## Princip

Steganogra pracuje s myšlenkou vizuální kryptografie: tajná informace se nerozluští výpočtem, ale prostým překrytím dvou obrazových vrstev.

Každý bod tajného obrazu se převede na malý blok černých a bílých subpixelů. Program vytvoří dvě vrstvy tak, aby:

- samotná vrstva neprozrazovala celý tajný obsah,
- po přesném překrytí vrstev vznikl čitelný výsledek,
- černé body tajného obrazu byly po překrytí tmavší než bílé body.

Při překrytí se používá logika OR: pokud je na daném místě černý bod alespoň v jedné vrstvě, bude černý i ve výsledku. Díky tomu lze vrstvy vytisknout na průhlednou fólii a zprávu přečíst bez dalšího programu.

## Dva režimy

### Vizuální kryptografie

V tomto režimu zadáváte jen tajný text nebo tajný obraz. Program z něj vytvoří dvě vrstvy, které samy o sobě vypadají jako náhodný šum. Tajná zpráva se objeví až po jejich překrytí.

Tento režim je vhodný, když chcete, aby jednotlivé vrstvy nepůsobily jako čitelný obrázek.

### Vizuální steganografie

V tomto režimu mají vrstvy vlastní viditelný obsah a zároveň dohromady skrývají třetí obsah.

Používají se tři vstupy:

- text nebo obrázek pro vrstvu 1,
- text nebo obrázek pro vrstvu 2,
- tajný text nebo obrázek, který se ukáže po překrytí.

Tento režim je vhodný pro demonstrace, hry, výukové materiály nebo situace, kdy mají jednotlivé vrstvy vypadat jako běžné obrázky.

## Spuštění programu

Nejjednodušší spuštění ve Windows:

```bat
spustit.bat
```

Případně lze program spustit přímo:

```bash
python steganogra_app.py
```

Pro běh aplikace je potřeba Python a knihovny uvedené v souboru `requirements.txt`, hlavně `PyQt6` a `Pillow`.

## Záložka Tvorba vrstev

Tato záložka slouží k vytvoření nových vrstev.

1. Vyberte režim: `Vizuální kryptografie` nebo `Vizuální steganografie`.
2. Zvolte velikost pixelového bloku: `1x`, `2x` nebo `3x`.
3. Zadejte text, případně vyberte obrázek tlačítkem `Obrazek`.
4. Nastavte velikost fontu a pozici textu.
5. Klikněte na `Generovat`.
6. V náhledu zkontrolujte vrstvu 1, vrstvu 2 a výsledek překrytí.
7. Podle potřeby posuňte vrstvu 2 myší nebo šipkami.
8. Exportujte výsledek jako PNG nebo PDF.

### Velikost pixelu

Velikost pixelového bloku určuje, jak jemná nebo odolná bude kresba:

| Volba | Výhoda | Nevýhoda |
| --- | --- | --- |
| `1x (4x4 px)` | nejjemnější kresba | vyžaduje velmi přesné zarovnání |
| `2x (8x8 px)` | dobrý kompromis a výchozí volba | méně detailů než `1x` |
| `3x (16x16 px)` | nejlepší pro ruční překrytí | hrubší obraz |

Pro první pokusy a tisk na běžné tiskárně je praktická volba `2x` nebo `3x`.

### Zdroj vrstvy 2

V režimu vizuální kryptografie lze vrstvu 2 vytvořit dvěma způsoby:

- `Random noise` vytvoří při každém generování nový náhodný šum.
- `Deterministic key` vytvoří vrstvu 2 ze SHA-256 proudu odvozeného ze zadaného slova nebo hesla.

Při stejném klíči, rozlišení a velikosti pixelu je vrstva 2 identická. Pro různé tajné vstupy pak vznikají různé soubory vrstvy 1, které lze číst se stejnou klíčovou vrstvou 2.

### Text a obrázky

Každé vstupní pole může obsahovat text. Místo textu lze vybrat obrázek. Program obrázek převede na černobílou mřížku a přizpůsobí ho rozměrům vrstvy.

Tlačítko `X` u vstupu odstraní vybraný obrázek a vrátí pole zpět k textu.

### Pozice textu

Text lze umístit:

- vodorovně vlevo, na střed nebo vpravo,
- svisle nahoru, na střed nebo dolů,
- jemným posunem pomocí hodnot `X` a `Y`.

Tlačítko `Vycentrovat` vrátí text zpět na střed.

## Export

### Export PNG

Tlačítko `Export PNG` uloží do vybrané složky tři soubory:

- `vrstva1.png`,
- `vrstva2.png`,
- `vysledek.png`.

Soubory `vrstva1.png` a `vrstva2.png` jsou určené pro tisk nebo další práci. Soubor `vysledek.png` je kontrolní náhled překrytí bez posunu.

### Export PDF

Tlačítko `Export PDF` vytvoří PDF se zdrojovými vrstvami. To je vhodné hlavně pro tisk, protože PDF lépe drží velikost stránky a je pohodlnější pro předání někomu dalšímu.

Výstup je připravený jako A4 při 150 DPI v orientaci na šířku.

## Záložka Kontrola překrytí

Tato záložka slouží ke kontrole už existujících vrstev.

Postup:

1. U položky `Vrstva 1` klikněte na `Otevrit` a vyberte první obrázek.
2. U položky `Vrstva 2` klikněte na `Otevrit` a vyberte druhý obrázek.
3. Klikněte na `Zobrazit prekryti`.
4. Posuňte vrstvu 2 myší nebo šipkami, dokud nebude výsledek čitelný.
5. Tlačítkem `Ulozit vysledek` můžete uložit aktuální překrytí.

Kontrola překrytí je užitečná při skenování, při práci s vrstvami z jiného zdroje nebo při hledání správného zarovnání.

## Doporučení pro tisk

- Tiskněte obě vrstvy se stejným nastavením tiskárny.
- Nepoužívejte automatické přizpůsobení stránce, pokud mění měřítko.
- Pro nejlepší výsledek tiskněte na průhlednou fólii.
- Pokud používáte papír, pomůže silné světlo za listy.
- Pro ruční překrytí zvolte větší pixelový blok, například `3x`.
- Pokud se tajná zpráva neukáže, nejčastější příčinou je posun nebo rozdílné měřítko výtisků.

## Bezpečnostní poznámka

Vizuální kryptografie je výborná pro demonstraci principu sdílení tajemství a pro jednoduché fyzické skrývání zpráv. Praktická bezpečnost ale závisí na tom, jak jsou vrstvy vytvořené, uložené, vytištěné a předané. Pokud má být obsah opravdu citlivý, nevkládejte obě vrstvy na stejné místo a neposílejte je stejným kanálem.

## Typický pracovní postup

1. Připravte krátký tajný text nebo jednoduchý černobílý obrázek.
2. V programu zvolte režim a velikost pixelu.
3. Vygenerujte vrstvy.
4. Zkontrolujte náhled překrytí.
5. Exportujte PNG nebo PDF.
6. Vytiskněte obě vrstvy.
7. Překryjte je a jemně dolaďte polohu.

Nejlépe fungují jednoduché, kontrastní motivy: velká písmena, krátká slova, QR kódy, symboly a siluety.
