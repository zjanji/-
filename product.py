# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, fields, sequence_ordered
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, Or
from trytond.tools import grouped_slice
from trytond.transaction import Transaction


class Category(metaclass=PoolMeta):
    __name__ = 'product.category'
    customs = fields.Boolean(
        "Customs",
        states={
            'readonly': Bool(Eval('childs', [0])) | Bool(Eval('parent')),
            })
    tariff_codes_parent = fields.Boolean("Use Parent's Tariff Codes",
        states={
            'invisible': ~Eval('customs', False),
            },
        help='Use the tariff codes defined on the parent category.')
    tariff_codes = fields.One2Many('product-customs.tariff.code',
        'product', 'Tariff Codes', order=[('sequence', 'ASC'), ('id', 'ASC')],
        states={
            'invisible': (Eval('tariff_codes_parent', False)
                | ~Eval('customs', False)),
            })

    @classmethod
    def __setup__(cls):
        super(Category, cls).__setup__()
        cls.parent.domain = [
            ('customs', '=', Eval('customs', False)),
            cls.parent.domain or []]
        cls.parent.states['required'] = Or(
            cls.parent.states.get('required', False),
            Eval('tariff_codes_parent', False))

    @classmethod
    def default_customs(cls):
        return False

    @classmethod
    def default_tariff_codes_parent(cls):
        return False

    @fields.depends('parent', '_parent_parent.customs', 'customs')
    def on_change_with_customs(self):
        if self.parent:
            return self.parent.customs
        return self.customs

    def get_tariff_codes(self, pattern):
        if not self.tariff_codes_parent:
            for link in self.tariff_codes:
                if link.tariff_code.match(pattern):
                    yield link.tariff_code
        else:
            yield from self.parent.get_tariff_codes(pattern)

    def get_tariff_code(self, pattern):
        try:
            return next(self.get_tariff_codes(pattern))
        except StopIteration:
            pass

    @classmethod
    def view_attributes(cls):
        return super(Category, cls).view_attributes() + [
            ('/form/notebook/page[@id="customs"]', 'states', {
                    'invisible': ~Eval('customs', False),
                    }),
            ]

    @classmethod
    def delete(cls, categories):
        pool = Pool()
        Product_TariffCode = pool.get('product-customs.tariff.code')
        products = [str(t) for t in categories]

        super(Category, cls).delete(categories)

        for products in grouped_slice(products):
            product_tariffcodes = Product_TariffCode.search([
                    'product', 'in', list(products),
                    ])
            Product_TariffCode.delete(product_tariffcodes)


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'
    customs_category = fields.Many2One('product.category', 'Customs Category',
        domain=[
            ('customs', '=', True),
            ],
        states={
            'required': Eval('tariff_codes_category', False),
            })
    tariff_codes_category = fields.Boolean("Use Category's Tariff Codes",
        help='Use the tariff codes defined on the category.')
    tariff_codes = fields.One2Many('product-customs.tariff.code',
        'product', 'Tariff Codes', order=[('sequence', 'ASC'), ('id', 'ASC')],
        states={
            'invisible': ((Eval('type') == 'service')
                | Eval('tariff_codes_category', False)),
            })
    country_of_origin = fields.Many2One(
        'country.country', "Country",
        states={
            'invisible': Eval('type') == 'service',
            })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        pool = Pool()
        Category = pool.get('product.category')
        sql_table = cls.__table__()
        category = Category.__table__()

        table = cls.__table_handler__(module_name)
        category_exists = table.column_exist('category')

        super(Template, cls).__register__(module_name)

        # Migration from 3.8: duplicate category into account_category
        if category_exists:
            # Only accounting category until now
            cursor.execute(*category.update([category.customs], [True]))
            cursor.execute(*sql_table.update(
                    [sql_table.customs_category],
                    [sql_table.category]))

    @classmethod
    def default_tariff_codes_category(cls):
        return False

    def get_tariff_codes(self, pattern):
        if not self.tariff_codes_category:
            for link in self.tariff_codes:
                if link.tariff_code.match(pattern):
                    yield link.tariff_code
        else:
            yield from self.customs_category.get_tariff_codes(pattern)

    def get_tariff_code(self, pattern):
        try:
            return next(self.get_tariff_codes(pattern))
        except StopIteration:
            pass

    @classmethod
    def view_attributes(cls):
        return super(Template, cls).view_attributes() + [
            ('//page[@id="customs"]', 'states', {
                    'invisible': Eval('type') == 'service',
                    }),
            ]

    @classmethod
    def delete(cls, templates):
        pool = Pool()
        Product_TariffCode = pool.get('product-customs.tariff.code')
        products = [str(t) for t in templates]

        super(Template, cls).delete(templates)

        for products in grouped_slice(products):
            product_tariffcodes = Product_TariffCode.search([
                    'product', 'in', list(products),
                    ])
            Product_TariffCode.delete(product_tariffcodes)


class Product_TariffCode(sequence_ordered(), ModelSQL, ModelView):
    'Product - Tariff Code'
    __name__ = 'product-customs.tariff.code'
    product = fields.Reference('Product', selection=[
            ('product.template', 'Template'),
            ('product.category', 'Category'),
            ], required=True)
    tariff_code = fields.Many2One('customs.tariff.code', 'Tariff Code',
        required=True, ondelete='CASCADE')

    def get_rec_name(self, name):
        return self.tariff_code.rec_name

    @classmethod
    def search_rec_name(cls, name, clause):
        return [('tariff_code.rec_name',) + tuple(clause[1:])]


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    def get_tariff_codes(self, pattern):
        yield from self.template.get_tariff_codes(pattern)

    def get_tariff_code(self, pattern):
        return self.template.get_tariff_code(pattern)
