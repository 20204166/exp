import random 

final = 0
number = 0


def generate_random_number() ->int:
    return random.randint(1, 1000)

def analyze_number(number: int) -> str:
    final = generate_random_number()
    if final % 2 == 0:
        number = final
        return "Less"
    if final % 2 == 1:
        number = final 
        return "Greater"
    return f"The number is {number} and the random number is {final}."

