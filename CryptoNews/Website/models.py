from django.db import models

# Create your models here.
class CryptoCurrency(models.Model):
    symbol = models.CharField(max_length=10, unique=True)
    full_name = models.CharField(max_length=100)
    current_price = models.DecimalField(max_digits=20, decimal_places=2)
    market_cap = models.DecimalField(max_digits=20, decimal_places=2)
def __str__(self):
    return self.symbol