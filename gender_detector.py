#!/usr/bin/env python3
"""
Détection de genre basée sur le prénom
Utilise une liste de prénoms masculins/féminins courants
"""

# Prénoms masculins courants (internationaux)
MALE_NAMES = {
    # Français
    'adam', 'adrien', 'alexandre', 'alexis', 'antoine', 'arthur', 'baptiste', 'benjamin',
    'bruno', 'charles', 'christophe', 'clément', 'damien', 'david', 'denis', 'dimitri',
    'edouard', 'emmanuel', 'eric', 'etienne', 'fabien', 'florian', 'francois', 'frederic',
    'gabriel', 'guillaume', 'hugo', 'jacques', 'jean', 'jerome', 'julien', 'kevin',
    'laurent', 'leo', 'louis', 'lucas', 'marc', 'mathieu', 'maxime', 'michel',
    'nathan', 'nicolas', 'olivier', 'patrick', 'paul', 'philippe', 'pierre', 'quentin',
    'raphael', 'remi', 'romain', 'sebastien', 'simon', 'stephane', 'sylvain', 'theo',
    'thomas', 'valentin', 'victor', 'vincent', 'xavier', 'yann', 'yannick', 'yves',

    # Anglais
    'aaron', 'andrew', 'anthony', 'austin', 'ben', 'bill', 'billy', 'bob', 'brad',
    'brandon', 'brian', 'bruce', 'bryan', 'carl', 'chad', 'charlie', 'chris', 'christian',
    'christopher', 'colin', 'connor', 'dan', 'daniel', 'danny', 'derek', 'donald', 'doug',
    'douglas', 'drew', 'dylan', 'ed', 'edward', 'eli', 'elijah', 'ethan', 'evan',
    'frank', 'fred', 'gary', 'george', 'greg', 'gregory', 'harry', 'henry', 'ian',
    'jack', 'jacob', 'jake', 'james', 'jason', 'jeff', 'jeffrey', 'jeremy', 'jesse',
    'jim', 'jimmy', 'joe', 'joel', 'john', 'johnny', 'jonathan', 'jordan', 'joseph',
    'josh', 'joshua', 'juan', 'justin', 'keith', 'ken', 'kenneth', 'kevin', 'kyle',
    'larry', 'liam', 'logan', 'luke', 'mark', 'martin', 'mason', 'matt', 'matthew',
    'max', 'michael', 'mike', 'nathan', 'nick', 'nicholas', 'noah', 'oliver', 'oscar',
    'owen', 'patrick', 'paul', 'peter', 'philip', 'randy', 'ray', 'richard', 'rick',
    'rob', 'robert', 'roger', 'ron', 'ronald', 'ross', 'russell', 'ryan', 'sam',
    'samuel', 'scott', 'sean', 'seth', 'shane', 'shawn', 'spencer', 'steve', 'steven',
    'ted', 'terry', 'tim', 'timothy', 'todd', 'tom', 'tommy', 'tony', 'travis',
    'trevor', 'troy', 'tyler', 'victor', 'walter', 'wayne', 'william', 'willie', 'zach', 'zachary',

    # Espagnol
    'alejandro', 'alfonso', 'andres', 'angel', 'antonio', 'carlos', 'cesar', 'diego',
    'eduardo', 'enrique', 'ernesto', 'fernando', 'francisco', 'gerardo', 'gonzalo',
    'guillermo', 'gustavo', 'hector', 'hernando', 'hugo', 'ignacio', 'javier', 'jesus',
    'jorge', 'jose', 'juan', 'julio', 'luis', 'manuel', 'marco', 'marcos', 'mario',
    'martin', 'miguel', 'nicolas', 'oscar', 'pablo', 'pedro', 'rafael', 'raul',
    'ricardo', 'roberto', 'rodrigo', 'salvador', 'santiago', 'sergio', 'victor',

    # Italien
    'alberto', 'alessandro', 'andrea', 'angelo', 'claudio', 'daniele', 'davide',
    'emanuele', 'fabio', 'federico', 'filippo', 'francesco', 'giacomo', 'giorgio',
    'giovanni', 'giuseppe', 'luca', 'luigi', 'marco', 'mario', 'massimo', 'matteo',
    'mauro', 'michele', 'nicola', 'paolo', 'pietro', 'riccardo', 'roberto', 'salvatore',
    'simone', 'stefano', 'tommaso', 'vincenzo', 'vittorio',

    # Arabe
    'ahmed', 'ali', 'amir', 'farid', 'hassan', 'hussein', 'ibrahim', 'karim', 'khalid',
    'mahmoud', 'mohamed', 'mohammed', 'mohammad', 'muhammad', 'mustafa', 'omar', 'rashid',
    'samir', 'tariq', 'youssef', 'yusuf', 'zaid',

    # Autres
    'abdul', 'akira', 'boris', 'chen', 'dmitri', 'erik', 'felix', 'hans', 'hiroshi',
    'ivan', 'jan', 'karl', 'kenji', 'klaus', 'lars', 'magnus', 'ming', 'olaf', 'pavel',
    'raj', 'sven', 'takeshi', 'wei', 'yuki', 'zhang',
}

# Prénoms féminins courants (internationaux)
FEMALE_NAMES = {
    # Français
    'alice', 'amelie', 'anna', 'anne', 'audrey', 'aurelie', 'brigitte', 'camille',
    'caroline', 'catherine', 'cecile', 'charlotte', 'chloe', 'christine', 'claire',
    'clementine', 'delphine', 'diane', 'elise', 'emilie', 'emma', 'estelle', 'eva',
    'florence', 'francoise', 'gabrielle', 'helene', 'isabelle', 'jeanne', 'julie',
    'juliette', 'laetitia', 'laura', 'laurence', 'lea', 'louise', 'lucie', 'madeleine',
    'manon', 'margot', 'marie', 'marine', 'mathilde', 'melanie', 'nathalie', 'nina',
    'pauline', 'rose', 'sarah', 'sophie', 'stephanie', 'sylvie', 'valentine', 'valerie',
    'vanessa', 'veronique', 'virginie', 'zoe',

    # Anglais
    'abigail', 'alexandra', 'alexis', 'allison', 'amanda', 'amber', 'amy', 'andrea',
    'angela', 'ann', 'anna', 'ashley', 'barbara', 'betty', 'beverly', 'brenda',
    'brittany', 'brooke', 'carol', 'carolyn', 'catherine', 'cheryl', 'christina',
    'christine', 'cindy', 'claire', 'crystal', 'cynthia', 'dana', 'danielle', 'deborah',
    'debra', 'denise', 'diana', 'diane', 'donna', 'dorothy', 'elizabeth', 'ellen',
    'emily', 'emma', 'erica', 'erin', 'evelyn', 'faith', 'frances', 'grace', 'hailey',
    'hannah', 'heather', 'helen', 'holly', 'irene', 'jacqueline', 'jane', 'janet',
    'janice', 'jean', 'jennifer', 'jessica', 'joan', 'joanne', 'joyce', 'judith',
    'judy', 'julia', 'julie', 'karen', 'katherine', 'kathleen', 'kathryn', 'kathy',
    'katie', 'kayla', 'kelly', 'kimberly', 'kristen', 'kristin', 'laura', 'lauren',
    'linda', 'lisa', 'lori', 'madison', 'margaret', 'maria', 'marie', 'marilyn',
    'martha', 'mary', 'megan', 'melissa', 'michelle', 'mildred', 'nancy', 'natalie',
    'nicole', 'olivia', 'pamela', 'patricia', 'paula', 'phyllis', 'rachel', 'rebecca',
    'rita', 'robin', 'ruth', 'samantha', 'sandra', 'sara', 'sarah', 'sharon', 'shirley',
    'sophia', 'stephanie', 'susan', 'tammy', 'teresa', 'tiffany', 'tina', 'tracy',
    'vanessa', 'victoria', 'virginia', 'wendy', 'whitney',

    # Espagnol
    'adriana', 'alejandra', 'alicia', 'ana', 'andrea', 'angelica', 'beatriz', 'camila',
    'carla', 'carmen', 'carolina', 'catalina', 'cecilia', 'claudia', 'cristina',
    'daniela', 'diana', 'elena', 'fernanda', 'gabriela', 'guadalupe', 'ines', 'irene',
    'isabel', 'jessica', 'jimena', 'julia', 'julieta', 'laura', 'leticia', 'lourdes',
    'lucia', 'luisa', 'luz', 'marcela', 'margarita', 'maria', 'mariana', 'martha',
    'mercedes', 'monica', 'natalia', 'nicole', 'patricia', 'paula', 'pilar', 'rosa',
    'sandra', 'silvia', 'sofia', 'valentina', 'valeria', 'veronica', 'victoria', 'ximena',

    # Italien
    'alessandra', 'alessia', 'anna', 'antonella', 'arianna', 'beatrice', 'bianca',
    'carla', 'carlotta', 'chiara', 'claudia', 'cristina', 'daniela', 'elena', 'eleonora',
    'elisa', 'elisabetta', 'federica', 'francesca', 'giada', 'giorgia', 'giovanna',
    'giulia', 'ilaria', 'irene', 'laura', 'lisa', 'lucia', 'luisa', 'marta', 'martina',
    'michela', 'monica', 'paola', 'roberta', 'sara', 'serena', 'silvia', 'simona',
    'sofia', 'stefania', 'valentina', 'veronica', 'viola',

    # Arabe
    'aisha', 'amina', 'fatima', 'hana', 'khadija', 'layla', 'leila', 'mariam', 'maryam',
    'nadia', 'noor', 'nour', 'rania', 'salma', 'sara', 'yasmin', 'yasmina', 'zahra', 'zara',

    # Autres
    'akiko', 'anastasia', 'anna', 'chen', 'elena', 'hana', 'ingrid', 'katarina', 'keiko',
    'li', 'maria', 'mei', 'natasha', 'olga', 'priya', 'sakura', 'svetlana', 'tatiana',
    'wei', 'xiao', 'yoko', 'yuki',
}

# Suffixes typiquement masculins
MALE_SUFFIXES = ['son', 'ton', 'dan', 'ian', 'ard', 'ert', 'ald', 'ley', 'vin', 'rick', 'ck']

# Suffixes typiquement féminins
FEMALE_SUFFIXES = ['ette', 'elle', 'ine', 'ina', 'ita', 'lyn', 'anna', 'essa', 'issa', 'ia', 'ie', 'ee', 'leigh', 'ley']

# Mots-clés féminins dans le nom/pseudo
FEMALE_KEYWORDS = {
    'pretty', 'queen', 'girl', 'princess', 'babe', 'baby', 'bella', 'beauty',
    'goddess', 'diva', 'lady', 'miss', 'mrs', 'mama', 'mom', 'mum', 'mother',
    'she', 'her', 'wife', 'wifey', 'girlfriend', 'gf', 'sis', 'sister',
    'barbie', 'kitty', 'bunny', 'honey', 'sweetie', 'cutie', 'hottie',
    'jazzy', 'angie', 'brina', 'lucy', 'elle', 'brooke', 'mell',
    'chica', 'reina', 'princesa', 'bella', 'bonita', 'linda', 'hermosa',
    'femme', 'fille', 'jolie', 'belle', 'mademoiselle', 'madame',
}

# Mots-clés masculins dans le nom/pseudo
MALE_KEYWORDS = {
    'king', 'boy', 'guy', 'man', 'mr', 'sir', 'lord', 'prince', 'duke',
    'dad', 'daddy', 'father', 'papa', 'bro', 'brother', 'husband', 'bf',
    'dude', 'chief', 'boss', 'alpha', 'gangsta', 'thug',
    'hombre', 'rey', 'principe', 'senor',
    'homme', 'monsieur', 'garcon', 'mec', 'gars',
}

# Table de conversion des caractères unicode stylisés vers ASCII
UNICODE_TO_ASCII = {}
# Bold letters 𝐀-𝐙, 𝐚-𝐳
for i, c in enumerate('𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙'):
    UNICODE_TO_ASCII[c] = chr(ord('A') + i)
for i, c in enumerate('𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳'):
    UNICODE_TO_ASCII[c] = chr(ord('a') + i)
# Italic letters 𝐴-𝑍, 𝑎-𝑧
for i, c in enumerate('𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍'):
    UNICODE_TO_ASCII[c] = chr(ord('A') + i)
for i, c in enumerate('𝑎𝑏𝑐𝑑𝑒𝑓𝑔𝑕𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧'):
    UNICODE_TO_ASCII[c] = chr(ord('a') + i)
# Script letters 𝒜-𝒵, 𝒶-𝓏
for i, c in enumerate('𝒜𝒝𝒞𝒟𝒠𝒡𝒢𝒣𝒤𝒥𝒦𝒧𝒨𝒩𝒪𝒫𝒬𝒭𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵'):
    UNICODE_TO_ASCII[c] = chr(ord('A') + i)
for i, c in enumerate('𝒶𝒷𝒸𝒹𝒺𝒻𝒼𝒽𝒾𝒿𝓀𝓁𝓂𝓃𝓄𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏'):
    UNICODE_TO_ASCII[c] = chr(ord('a') + i)
# More script variants
for i, c in enumerate('𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩'):
    UNICODE_TO_ASCII[c] = chr(ord('A') + i)
for i, c in enumerate('𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃'):
    UNICODE_TO_ASCII[c] = chr(ord('a') + i)


def normalize_unicode(text: str) -> str:
    """Convertit les caractères unicode stylisés en ASCII normal."""
    result = []
    for c in text:
        if c in UNICODE_TO_ASCII:
            result.append(UNICODE_TO_ASCII[c])
        else:
            result.append(c)
    return ''.join(result)


def detect_gender(name: str) -> str:
    """
    Détecte le genre probable basé sur le prénom.

    Returns:
        'male', 'female', ou 'unknown'
    """
    if not name:
        return 'unknown'

    # Normaliser les caractères unicode stylisés
    normalized_name = normalize_unicode(name)

    # Convertir en minuscules pour la recherche
    name_lower = normalized_name.lower()

    # Vérifier les mots-clés dans le nom complet (priorité haute)
    for keyword in FEMALE_KEYWORDS:
        if keyword in name_lower:
            return 'female'

    for keyword in MALE_KEYWORDS:
        if keyword in name_lower:
            return 'male'

    # Extraire le premier mot (prénom)
    first_name = name_lower.split()[0].strip() if name_lower else ''

    # Nettoyer le prénom (enlever emojis, chiffres, caractères spéciaux)
    clean_name = ''.join(c for c in first_name if c.isalpha())

    if not clean_name:
        return 'unknown'

    # Vérifier dans les listes de prénoms
    if clean_name in MALE_NAMES:
        return 'male'
    if clean_name in FEMALE_NAMES:
        return 'female'

    # Vérifier les suffixes
    for suffix in FEMALE_SUFFIXES:
        if clean_name.endswith(suffix) and len(clean_name) > len(suffix) + 1:
            return 'female'

    for suffix in MALE_SUFFIXES:
        if clean_name.endswith(suffix) and len(clean_name) > len(suffix) + 1:
            return 'male'

    # Heuristiques supplémentaires
    if clean_name.endswith('a') and len(clean_name) > 2:
        # Beaucoup de prénoms féminins se terminent par 'a'
        return 'female'

    if clean_name.endswith('o') and len(clean_name) > 2:
        # Beaucoup de prénoms masculins se terminent par 'o'
        return 'male'

    return 'unknown'


def get_gender_emoji(gender: str) -> str:
    """Retourne un emoji pour le genre."""
    if gender == 'male':
        return '👨'
    elif gender == 'female':
        return '👩'
    return '❓'


if __name__ == '__main__':
    # Tests
    test_names = [
        'John Smith', 'Marie Dupont', 'Ahmed Hassan', 'Sakura Tanaka',
        'Chris Taylor', 'Alex Johnson', 'Roberto Garcia', 'Fatima Ali',
        'Unknown123', '🔥FireKing🔥', 'Jean-Pierre', 'Maria-Elena',
        'Kyle', 'Jessica', 'Mohamed', 'Sophia', 'Ryan', 'Emma'
    ]

    for name in test_names:
        gender = detect_gender(name)
        emoji = get_gender_emoji(gender)
        print(f"{emoji} {name}: {gender}")
