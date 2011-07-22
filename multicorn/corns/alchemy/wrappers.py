# -*- coding: utf-8 -*-
# Copyright © 2008-2011 Kozea/
# This file is part of Multicorn, licensed under a 3-clause BSD license.

from ...requests import requests, wrappers, types, CONTEXT as c
from . import Alchemy, InvalidRequestException

from sqlalchemy import sql as sqlexpr, Unicode
from sqlalchemy.sql import expression

import re

class Context(object):

    def __init__(self, query, type):
        self.type = type
        self.query = query


def type_context(context):
    return tuple([c.type for c in context])

class AlchemyWrapper(wrappers.RequestWrapper):
    class_map = wrappers.RequestWrapper.class_map.copy()

    def to_alchemy(self, query, contexts=()):
        raise NotImplementedError()

    def extract_tables(self):
        raise NotImplementedError()

    def is_valid(self, contexts=()):
        raise NotImplementedError()


@AlchemyWrapper.register_wrapper(requests.FilterRequest)
class FilterWrapper(wrappers.FilterWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        type = self.subject.return_type(type_context(contexts))
        contexts = contexts + (Context(query, type.inner_type),)
        where_clause = self.predicate.to_alchemy(query, contexts)
        return query.where(where_clause)

    def extract_tables(self):
        return self.subject.extract_tables() + self.predicate.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        self.predicate.is_valid(contexts +
                (self.subject.return_type(contexts).inner_type,))


@AlchemyWrapper.register_wrapper(requests.StoredItemsRequest)
class StoredItemsWrapper(wrappers.StoredItemsWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        for c in sorted(self.aliased_table.c, key = lambda x: x.key):
            query = query.column(c.label(c.key))
        if contexts:
            return query.apply_labels()
        return query

    def extract_tables(self):
        self.aliased_table = self.storage.table.alias()
        return (self.aliased_table,)

    def is_valid(self, contexts=()):
        pass

@AlchemyWrapper.register_wrapper(requests.ContextRequest)
class ContextWrapper(wrappers.ContextWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = contexts[self.scope_depth - 1].query
        if not isinstance(self.return_type(type_context(contexts)),
                (types.List, types.Dict)):
           # Context is a scalar, we should have only one column
           return list(query.c)[0].proxies[-1]
        return query

    def extract_tables(self):
        # A context switch does not introduce new tables
        return tuple()

    def is_valid(self, contexts=()):
        if len(contexts) <= self.scope_depth:
            raise InvalidRequestException(self, "Invalid Context Request:\
                    no %sth parent scope" % self.scope_depth)

@AlchemyWrapper.register_wrapper(requests.StrRequest)
class StrWrapper(wrappers.StrWrapper, AlchemyWrapper):

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts=()):
        pass

    def to_alchemy(self, query, contexts=()):
        subject = self.subject.to_alchemy(query, contexts)
        return expression.cast(subject, Unicode)


@AlchemyWrapper.register_wrapper(requests.UpperRequest)
class UpperWrapper(wrappers.UpperWrapper, AlchemyWrapper):

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts=()):
        pass

    def to_alchemy(self, query, contexts=()):
        subject = self.subject.to_alchemy(query, contexts)
        return query.with_only_columns([expression.func.upper(subject)])

@AlchemyWrapper.register_wrapper(requests.LowerRequest)
class LowerWrapper(wrappers.LowerWrapper, AlchemyWrapper):

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts=()):
        pass

    def to_alchemy(self, query, contexts=()):
        subject = self.subject.to_alchemy(query, contexts)
        return query.with_only_columns([expression.func.lower(subject)])


@AlchemyWrapper.register_wrapper(requests.RegexRequest)
class RegexWrapper(wrappers.RegexWrapper, AlchemyWrapper):

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        if not isinstance(self.other, wrappers.LiteralWrapper):
            raise InvalidRequestException(self, "Regex support only works with"
                "literals in alchemy")
        value = self.other.value
        value = value.replace('_', '\_')
        # Escaping chars
        value = value.replace('%', '\%')
        value = value.replace('.', '_')
        value = value.replace('$', '\$')
        if value.startswith('^'):
            value = value.strip('^')
        else:
            value = '%' + value
        if value.endswith('$'):
            value = value.strip('$')
        else:
            value = value + '%'
        if value != re.escape(value):
            raise InvalidRequestException(self, "Regex only supports '.*',.,^,$'")
        self.value = value

    def to_alchemy(self, query, contexts=()):
        subject = self.subject.to_alchemy(query, contexts)
        return subject.like(self.value)




@AlchemyWrapper.register_wrapper(requests.LiteralRequest)
class LiteralWrapper(wrappers.LiteralWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.value

    def extract_tables(self):
        return tuple()

    def is_valid(self, contexts=()):
       # TODO: raise on invalid Types
       pass


@AlchemyWrapper.register_wrapper(requests.AttributeRequest)
class AttributeWrapper(wrappers.AttributeWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        return query.c[self.attr_name].proxies[-1]

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        return_type = self.subject.return_type(contexts)
        # TODO: manage attr getters on date objects, maybe
        if not isinstance(return_type, types.Dict):
            raise InvalidRequestException(self, "Cannot access attribute in a \
                    non-dict context")


class BinaryOperationWrapper(AlchemyWrapper):

    def extract_tables(self):
        return self.subject.extract_tables() + self.other.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        self.other.is_valid(contexts)

    def left_column(self, query, contexts):
        subject = self.subject.to_alchemy(query, contexts)
        if isinstance(subject, sqlexpr.Selectable):
            return list(subject.c)[0].proxies[-1]
        return subject

    def right_column(self, query, contexts):
        other = self.other.to_alchemy(query, contexts)
        if isinstance(other, sqlexpr.Selectable):
            return list(other.c)[0].proxies[-1]
        return other



@AlchemyWrapper.register_wrapper(requests.AndRequest)
class AndWrapper(wrappers.AndWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return sqlexpr.and_(self.subject.to_alchemy(query, contexts),
                    self.other.to_alchemy(query, contexts))


@AlchemyWrapper.register_wrapper(requests.OrRequest)
class OrWrapper(wrappers.OrWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return sqlexpr.or_(self.subject.to_alchemy(query, contexts),
                    self.other.to_alchemy(query, contexts))


@AlchemyWrapper.register_wrapper(requests.EqRequest)
class EqWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) ==\
                self.right_column(query, contexts)


@AlchemyWrapper.register_wrapper(requests.NeRequest)
class NeWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) !=\
                self.right_column(query, contexts)

@AlchemyWrapper.register_wrapper(requests.LtRequest)
class LtWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) <\
                self.right_column(query, contexts)

@AlchemyWrapper.register_wrapper(requests.GtRequest)
class GtWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) >\
                self.right_column(query, contexts)

@AlchemyWrapper.register_wrapper(requests.LeRequest)
class LeWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) <=\
                self.right_column(query, contexts)

@AlchemyWrapper.register_wrapper(requests.GeRequest)
class GeWrapper(wrappers.BooleanOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.left_column(query, contexts) >=\
                self.right_column(query, contexts)

@AlchemyWrapper.register_wrapper(requests.AddRequest)
class AddWrapper(wrappers.AddWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        subject = self.subject.to_alchemy(query, contexts)
        other_base = query.with_only_columns([])
        other = self.other.to_alchemy(other_base, contexts)
        subject_type = self.subject.return_type(type_context(contexts))
        other_type = self.other.return_type(type_context(contexts))
        # Dict addition is a mapping merge
        if all(isinstance(x, types.Dict) for x in (subject_type, other_type)):
            for c in sorted(subject.c, key=lambda x : x.key):
                other = other.column(c.proxies[-1])
            return other.correlate(subject)
        elif all(isinstance(x, types.List) for x in (subject_type, other_type)):
            return subject.union(other)
        else:
            return subject + other


@AlchemyWrapper.register_wrapper(requests.SubRequest)
class SubWrapper(wrappers.ArithmeticOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.subject.to_alchemy(query, contexts) -\
                self.other.to_alchemy(query, contexts)

@AlchemyWrapper.register_wrapper(requests.MulRequest)
class MulWrapper(wrappers.ArithmeticOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.subject.to_alchemy(query, contexts) *\
                self.other.to_alchemy(query, contexts)

@AlchemyWrapper.register_wrapper(requests.DivRequest)
class DivWrapper(wrappers.ArithmeticOperationWrapper, BinaryOperationWrapper):

    def to_alchemy(self, query, contexts=()):
        return self.subject.to_alchemy(query, contexts) /\
                self.other.to_alchemy(query, contexts)

@AlchemyWrapper.register_wrapper(requests.MapRequest)
class MapWrapper(wrappers.MapWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        type = self.subject.return_type(type_context(contexts))
        contexts = contexts + (Context(query, type.inner_type),)
        select = self.new_value.to_alchemy(query, contexts)
        if not isinstance(select, expression.Selectable):
            if not hasattr(select, '__iter__'):
                select = [select]
            return query.with_only_columns(select)
        return select

    def extract_tables(self):
        return self.subject.extract_tables() + self.new_value.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        return_type = self.subject.return_type(contexts)
        if not isinstance(return_type, types.List):
            raise InvalidRequestException(self, "Cannot apply map to the type\
                                                %s" % return_type.type)
        contexts = contexts + (return_type.inner_type,)
        self.new_value.is_valid(contexts)

@AlchemyWrapper.register_wrapper(requests.DictRequest)
class DictWrapper(wrappers.DictWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        selects = []
        for key, request in sorted(self.value.iteritems()):
            return_type = request.return_type(type_context(contexts))
            req = request.to_alchemy(query, contexts)
            if return_type.type == list:
                raise ValueError("SQLAlchemy cannot return\
                        lists as part of a dict")
            elif isinstance(req, sqlexpr.Selectable):
                # If it is a dict, ensure that names dont collide
                if len(req.c) == 1:
                    selects.append(list(req.c)[0].proxies[-1].label(key))
                else:
                    for c in req.c:
                        selects.append(c.proxies[-1].label("__%s_%s__" % (key, c.name)))
                query = req.correlate(query)
            else:
                selects.append(req.label(key))
        return query.with_only_columns(selects)

    def is_valid(self, contexts):
        for req in self.value.values():
            req.is_valid(contexts)
            return_type = req.return_type(contexts)
            if return_type.type == list:
                raise InvalidRequestException(self, "Cannot fetch a list\
                        as a mapping value")

    def extract_tables(self):
        return reduce(lambda x, y: x + y, (request.extract_tables()
                        for request in self.value.values()))


@AlchemyWrapper.register_wrapper(requests.GroupbyRequest)
class GroupbyWrapper(wrappers.GroupbyWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        type = self.subject.return_type(type_context(contexts))
        key = self.key.to_alchemy(query, contexts +
                (Context(query, type.inner_type),))
        group = self.aggregates.to_alchemy(query, contexts +
                (Context(query, type),))
        group = group.group_by(key)
        group = group.column(key.label('key'))
        return group

    def extract_tables(self):
        return self.subject.extract_tables() +\
               self.key.extract_tables() +\
               self.aggregates.extract_tables()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        type = self.subject.return_type(contexts)
        self.key.is_valid(contexts + (type.inner_type,))
        self.aggregates.is_valid(contexts + (type,))


@AlchemyWrapper.register_wrapper(requests.SortRequest)
class SortWrapper(wrappers.SortWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        type = self.subject.return_type(type_context(contexts))
        contexts = contexts + (Context(query, type.inner_type,),)
        keys = []
        for key, reverse in self.sort_keys:
            sqlkey = key.to_alchemy(query, contexts)
            if reverse:
                keys.append(sqlexpr.desc(sqlkey))
            else:
                keys.append(sqlexpr.asc(sqlkey))
        return query.order_by(*keys)

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        contexts = contexts + (self.subject.return_type(contexts).inner_type,)
        for key, _ in self.sort_keys:
            key.is_valid(contexts)

    def extract_tables(self):
        return reduce(lambda x, y: x+y, [key.extract_tables()
            for key, _ in self.sort_keys], self.subject.extract_tables())

@AlchemyWrapper.register_wrapper(requests.OneRequest)
class OneWrapper(wrappers.OneWrapper, AlchemyWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        if contexts:
            # We are in a subquery, no limit to append!
            return query
        return query.limit(1)

    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts):
        self.subject.is_valid(contexts)
        if contexts:
            raise InvalidRequestException(self, "This request is not doable!")

class AggregateWrapper(AlchemyWrapper):


    def extract_tables(self):
        return self.subject.extract_tables()

    def is_valid(self, contexts):
        self.subject.is_valid(contexts)
        type = self.subject.return_type(contexts)
        if not isinstance(type, types.List):
            raise InvalidRequestException(self, "Cannot perform a sum on something\
                    which isn't a list")


@AlchemyWrapper.register_wrapper(requests.LenRequest)
class LenWrapper(wrappers.LenWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        return query.with_only_columns([expression.func.count(1)])


    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)



@AlchemyWrapper.register_wrapper(requests.SumRequest)
class SumWrapper(wrappers.AggregateWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        column = list(query.c)[0]
        return query.with_only_columns([expression.func.sum(column)])


    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)


@AlchemyWrapper.register_wrapper(requests.MaxRequest)
class MaxWrapper(wrappers.AggregateWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        column = list(query.c)[0]
        return query.with_only_columns([expression.func.max(column)])

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)


@AlchemyWrapper.register_wrapper(requests.MinRequest)
class MinWrapper(wrappers.AggregateWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        column = list(query.c)[0]
        return query.with_only_columns([expression.func.min(column)])


    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)


@AlchemyWrapper.register_wrapper(requests.DistinctRequest)
class DistinctWrapper(wrappers.AggregateWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        query = self.subject.to_alchemy(query, contexts)
        return query.distinct()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)


@AlchemyWrapper.register_wrapper(requests.SliceRequest)
class SliceWrapper(wrappers.PreservingWrapper, AggregateWrapper):

    def to_alchemy(self, query, contexts=()):
        type = self.subject.return_type(contexts)
        query = self.subject.to_alchemy(query, contexts)
        if isinstance(type, types.List):
            if self.slice.stop:
                stop = self.slice.stop - (self.slice.start or 0)
                query = query.limit(stop)
            if self.slice.start:
                query = query.offset(self.slice.start)
            return query.alias().select()

    def is_valid(self, contexts=()):
        self.subject.is_valid(contexts)
        if self.slice.step:
            raise InvalidRequestException(self,
                    "Can't manage slice requests with steps")
        if any((x or 0) < 0 for x in (self.slice.start, self.slice.stop)):
            raise InvalidRequestException(self,
                    "Negative slice indexes not supported")
        if not isinstance(self.subject.return_type(contexts), types.List):
            raise InvalidRequestException(self,
                    "Slice is not managed on not list objects")
