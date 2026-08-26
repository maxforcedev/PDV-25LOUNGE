from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.companies.models import (
    AccessProfile, Branch, Company, Status, UserBranchAccess, UserCompanyAccess,
    UserPermissionBlock,
)
from apps.companies.rbac import (
    ALL_PERMISSION_CODES, OPERATING_PERMISSION_CODES, PERMISSION_SCOPE_BY_CODE,
)
from apps.companies.selectors import (
    accessible_branches,
    accessible_companies,
    branch_permission_codes,
    company_permission_codes,
    user_has_company_permission,
)
from apps.companies.services import replace_user_accesses

from .models import User


def support_effective_permission_codes(support_session):
    if support_session.mode == 'READ_WRITE':
        return set(ALL_PERMISSION_CODES)
    return {
        code for code in ALL_PERMISSION_CODES
        if (
            code.endswith('.view')
            or '.view_' in code
            or code.startswith(('reports.', 'dashboard.', 'audit_logs.'))
        )
    }


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class UserSerializer(serializers.ModelSerializer):
    is_superuser = serializers.BooleanField(read_only=True)
    companies = serializers.SerializerMethodField()
    branches = serializers.SerializerMethodField()
    permission_blocks = serializers.SerializerMethodField()
    permission_scopes = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'can_login',
            'user_type',
            'first_name',
            'last_name',
            'is_active',
            'is_superuser',
            'companies',
            'branches',
            'permission_blocks',
            'permission_scopes',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'email',
            'is_active',
            'is_superuser',
            'companies',
            'branches',
            'permission_blocks',
            'permission_scopes',
            'created_at',
            'updated_at',
        )

    def get_permission_scopes(self, user):
        return PERMISSION_SCOPE_BY_CODE

    def _visible_company_ids(self, user):
        request = self.context.get('request')
        if not request or request.user.is_superuser or request.user.pk == user.pk:
            return None
        parser_context = getattr(request, 'parser_context', None) or {}
        action = getattr(parser_context.get('view'), 'action', None)
        permission_code = {
            'update': 'users.change',
            'partial_update': 'users.change',
            'activate': 'users.change_status',
            'deactivate': 'users.change_status',
        }.get(action, 'users.view')
        return set(
            accessible_companies(request.user, permission_code).values_list(
                'id', flat=True
            )
        )

    def _active_company_accesses(self, user):
        accesses = user.company_accesses.filter(
            is_active=True,
            saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).select_related('company')
        company_ids = self._visible_company_ids(user)
        if company_ids is not None:
            accesses = accesses.filter(company_id__in=company_ids)
        return accesses

    def get_companies(self, user):
        from apps.saas.services import resolve_effective_status

        request = self.context.get('request')
        support_session = getattr(request, 'support_session', None) if request else None
        if support_session and not support_session.impersonated_user_id:
            company = support_session.company
            effective = resolve_effective_status(company)
            permissions = support_effective_permission_codes(support_session)
            return [{
                'id': company.id,
                'trade_name': company.trade_name,
                'status': company.status,
                'is_owner': False,
                'effective_status': effective['status'],
                'can_operate': effective['can_operate'],
                'access_profile': {'id': None, 'name': 'Suporte da plataforma'},
                'permissions': sorted(permissions - OPERATING_PERMISSION_CODES),
                'support_context': True,
            }]
        if user.is_superuser:
            permissions = sorted(ALL_PERMISSION_CODES)
            owned_company_ids = set(
                user.company_accesses.filter(is_owner=True, is_active=True).values_list(
                    'company_id', flat=True
                )
            )
            companies = []
            for company in Company.objects.all():
                effective = resolve_effective_status(company)
                companies.append({
                    'id': company.id,
                    'trade_name': company.trade_name,
                    'status': company.status,
                    'is_owner': company.id in owned_company_ids,
                    'effective_status': effective['status'],
                    'can_operate': effective['can_operate'],
                    'access_profile': {'id': None, 'name': 'Superusuario'},
                    'permissions': permissions,
                })
            return companies
        companies = []
        for access in self._active_company_accesses(user):
            effective = resolve_effective_status(access.company)
            companies.append({
                'id': access.company_id,
                'trade_name': access.company.trade_name,
                'status': access.company.status,
                'is_owner': access.is_owner,
                'saas_status': access.saas_status,
                'effective_status': effective['status'],
                'can_operate': effective['can_operate'],
                'permissions': sorted(
                    company_permission_codes(user, access.company_id) - OPERATING_PERMISSION_CODES
                ),
            })
        return companies

    def get_branches(self, user):
        from apps.companies.features import branch_feature_states

        if not user.can_login or not user.is_active:
            return []
        request = self.context.get('request')
        support_session = getattr(request, 'support_session', None) if request else None
        if support_session and not support_session.impersonated_user_id:
            permissions = sorted(
                support_effective_permission_codes(support_session)
                & OPERATING_PERMISSION_CODES
            )
            return [
                {
                    'id': branch.id,
                    'name': branch.name,
                    'company_id': branch.company_id,
                    'status': branch.status,
                    'access_profile': {
                        'id': None,
                        'name': 'Suporte da plataforma',
                    },
                    'permissions': permissions,
                    'features': branch_feature_states(branch),
                    'support_context': True,
                }
                for branch in Branch.objects.select_related('company', 'settings').filter(
                    company_id=support_session.company_id,
                    company__status=Status.ACTIVE,
                    status=Status.ACTIVE,
                ).order_by('name', 'id')
            ]
        if user.is_superuser:
            permissions = sorted(ALL_PERMISSION_CODES)
            return [
                {
                    'id': branch.id,
                    'name': branch.name,
                    'company_id': branch.company_id,
                    'status': branch.status,
                    'access_profile': None,
                    'permissions': permissions,
                    'features': branch_feature_states(branch),
                }
                for branch in Branch.objects.select_related('company', 'settings').all()
            ]
        company_ids = self._visible_company_ids(user)
        accesses = user.branch_accesses.filter(
            is_active=True,
            access_profile__status=Status.ACTIVE,
            branch__company__user_accesses__user=user,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).select_related(
            'branch', 'branch__company', 'branch__settings', 'access_profile'
        ).prefetch_related(
            'access_profile__permissions'
        )
        if company_ids is not None:
            accesses = accesses.filter(branch__company_id__in=company_ids)
            accesses = accesses.filter(
                branch_id__in=accessible_branches(
                    self.context['request'].user
                ).values_list('id', flat=True)
            )
        return [
            {
                'id': access.branch_id,
                'name': access.branch.name,
                'company_id': access.branch.company_id,
                'status': access.branch.status,
                'access_profile': {
                    'id': access.access_profile_id,
                    'name': access.access_profile.name,
                },
                'permissions': sorted(
                    branch_permission_codes(user, access.branch_id) & OPERATING_PERMISSION_CODES
                ),
                'features': branch_feature_states(access.branch),
            }
            for access in accesses.distinct()
        ]

    def get_permission_blocks(self, user):
        request = self.context.get('request')
        company_ids = self._visible_company_ids(user)
        blocks = UserPermissionBlock.objects.filter(user=user, is_active=True).select_related(
            'company', 'branch', 'permission'
        )
        if company_ids is not None:
            blocks = blocks.filter(company_id__in=company_ids)
        return [
            {
                'id': block.pk,
                'company': block.company_id,
                'company_name': block.company.trade_name,
                'branch': block.branch_id,
                'branch_name': block.branch.name if block.branch_id else None,
                'permission_code': block.permission.code,
                'permission_label': block.permission.label,
                'reason': block.reason,
            }
            for block in blocks
        ]


class BranchAccessWriteSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField(min_value=1)
    access_profile_id = serializers.IntegerField(min_value=1)


class CompanyAccessWriteSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(min_value=1)
    access_profile_id = serializers.IntegerField(
        min_value=1, allow_null=True, required=False, default=None
    )
    branch_accesses = BranchAccessWriteSerializer(
        many=True,
        allow_empty=True,
    )


class UserManagementSerializer(UserSerializer):
    email = serializers.EmailField(
        required=False, allow_blank=True, allow_null=True
    )
    password = serializers.CharField(
        required=False,
        trim_whitespace=False,
        write_only=True,
    )
    company_accesses = CompanyAccessWriteSerializer(
        many=True,
        required=False,
        write_only=True,
    )

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('password', 'company_accesses')
        read_only_fields = (
            'id',
            'is_active',
            'is_superuser',
            'companies',
            'branches',
            'created_at',
            'updated_at',
        )

    def validate_email(self, value):
        if not value:
            return None
        email = User.objects.normalize_email(value).lower()
        queryset = User.objects.filter(email__iexact=email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Este e-mail ja esta em uso.')
        return email

    def _validate_company_accesses(self, items, permission_code):
        request = self.context['request']
        company_ids = [item['company_id'] for item in items]
        if len(company_ids) != len(set(company_ids)):
            raise serializers.ValidationError(
                {'company_accesses': 'Não repita a mesma empresa.'}
            )

        companies = Company.objects.in_bulk(company_ids)
        if len(companies) != len(company_ids):
            raise serializers.ValidationError(
                {'company_accesses': 'Uma ou mais empresas nao existem.'}
            )

        normalized = []
        for item in items:
            company = companies[item['company_id']]
            if not user_has_company_permission(request.user, company.id, permission_code):
                raise PermissionDenied(
                    'Você não possui permissão em todas as empresas informadas.'
                )
            profile = None
            if item.get('access_profile_id') is not None:
                try:
                    profile = AccessProfile.objects.get(
                        id=item['access_profile_id'],
                        company=company,
                        status=Status.ACTIVE,
                    )
                except AccessProfile.DoesNotExist as error:
                    raise serializers.ValidationError(
                        {'company_accesses': 'O perfil nao pertence a empresa ou esta inativo.'}
                    ) from error

            branch_items = item['branch_accesses']
            branch_ids = [branch_item['branch_id'] for branch_item in branch_items]
            if len(branch_ids) != len(set(branch_ids)):
                raise serializers.ValidationError(
                    {'company_accesses': 'Não repita a mesma filial.'}
                )
            existing_branch_ids = set()
            if self.instance:
                existing_branch_ids = set(
                    self.instance.branch_accesses.filter(
                        branch_id__in=branch_ids,
                        branch__company=company,
                        is_active=True,
                    ).values_list('branch_id', flat=True)
                )
            branches = Branch.objects.filter(
                Q(status=Status.ACTIVE) | Q(id__in=existing_branch_ids),
                id__in=branch_ids,
                company=company,
            ).in_bulk()
            if len(branches) != len(branch_ids):
                raise serializers.ValidationError(
                    {'company_accesses': 'Uma filial nao existe ou pertence a outra empresa.'}
                )
            if not request.user.is_superuser:
                actor_branch_ids = set(
                    accessible_branches(request.user)
                    .filter(company=company)
                    .values_list('id', flat=True)
                )
                if set(branch_ids) - actor_branch_ids:
                    raise PermissionDenied(
                        'Uma ou mais filiais estao fora do contexto autorizado.'
                    )
                company_profile_codes = set()
                if profile:
                    company_profile_codes = set(
                        profile.permissions.filter(status=Status.ACTIVE).values_list(
                            'code', flat=True
                        )
                    )
                company_profile_codes -= OPERATING_PERMISSION_CODES
                actor_company_codes = company_permission_codes(request.user, company.id)
                actor_company_codes -= OPERATING_PERMISSION_CODES
                if company_profile_codes - actor_company_codes:
                    raise PermissionDenied(
                        'Você não pode atribuir um perfil com permissões que não possui.'
                    )
            normalized_branches = []
            for branch_item in branch_items:
                try:
                    branch_profile = AccessProfile.objects.get(
                        id=branch_item['access_profile_id'],
                        company=company,
                        status=Status.ACTIVE,
                    )
                except AccessProfile.DoesNotExist as error:
                    raise serializers.ValidationError(
                        {'company_accesses': 'Um perfil de filial nao pertence a empresa ou esta inativo.'}
                    ) from error
                branch = branches[branch_item['branch_id']]
                if not request.user.is_superuser:
                    requested_codes = set(
                        branch_profile.permissions.filter(status=Status.ACTIVE).values_list(
                            'code', flat=True
                        )
                    )
                    requested_codes &= OPERATING_PERMISSION_CODES
                    if requested_codes - branch_permission_codes(request.user, branch.id):
                        raise PermissionDenied(
                            'Você não pode atribuir um perfil de filial com permissões que não possui.'
                        )
                normalized_branches.append(
                    {'branch': branch, 'access_profile': branch_profile}
                )
            normalized.append(
                {
                    'company': company,
                    'access_profile': profile,
                    'branch_accesses': normalized_branches,
                }
            )
        return normalized

    def validate(self, attrs):
        request = self.context['request']
        can_login = attrs.get(
            'can_login', getattr(self.instance, 'can_login', True)
        )
        enabling_login = bool(
            self.instance and not self.instance.can_login and can_login
        )
        if can_login and (not self.instance or enabling_login) and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'A senha e obrigatoria.'})
        email = attrs.get('email', getattr(self.instance, 'email', None))
        if can_login and not email:
            raise serializers.ValidationError(
                {'email': 'O e-mail é obrigatório para usuários com login.'}
            )
        if not self.instance and not attrs.get('company_accesses'):
            raise serializers.ValidationError(
                {'company_accesses': 'Informe ao menos um acesso de empresa.'}
            )

        password = attrs.get('password')
        if password:
            candidate = self.instance or User()
            for attribute in ('email', 'first_name', 'last_name'):
                if attribute in attrs:
                    setattr(candidate, attribute, attrs[attribute])
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as error:
                raise serializers.ValidationError({'password': list(error.messages)}) from error

        permission_code = 'users.change' if self.instance else 'users.add'
        current_company_ids = set()
        if self.instance:
            current_company_ids = set(
                self.instance.company_accesses.filter(is_active=True).values_list(
                    'company_id', flat=True
                )
            )
            if self.instance.is_superuser and not request.user.is_superuser:
                raise PermissionDenied('Você não pode alterar um superusuário.')
            if any(
                not user_has_company_permission(request.user, company_id, permission_code)
                for company_id in current_company_ids
            ):
                raise PermissionDenied(
                    'O usuário possui acessos fora do seu contexto autorizado.'
                )

        if 'company_accesses' in attrs:
            if self.instance and self.instance.pk == request.user.pk:
                raise serializers.ValidationError(
                    {'company_accesses': 'Você não pode alterar os próprios acessos.'}
                )
            changed_company_ids = current_company_ids | {
                item['company_id'] for item in attrs['company_accesses']
            }
            if self.instance and not request.user.is_superuser:
                visible_branch_ids = set(
                    accessible_branches(request.user)
                    .filter(company_id__in=changed_company_ids)
                    .values_list('id', flat=True)
                )
                hidden_target_ids = set(
                    self.instance.branch_accesses.filter(
                        is_active=True,
                        branch__company_id__in=changed_company_ids,
                    ).values_list('branch_id', flat=True)
                ) - visible_branch_ids
                if hidden_target_ids:
                    raise PermissionDenied(
                        'O usuário possui filiais fora do seu contexto autorizado.'
                    )
            attrs['company_accesses'] = self._validate_company_accesses(
                attrs['company_accesses'], permission_code
            )

        accesses = attrs.get('company_accesses')
        if not can_login and accesses is not None and any(
            item['branch_accesses']
            for item in accesses
        ):
            raise serializers.ValidationError({
                'company_accesses': 'Usuarios sem login nao podem possuir acessos de filial.'
            })

        if can_login:
            if accesses is not None:
                has_valid_links = any(
                    item['branch_accesses']
                    for item in accesses
                )
            elif self.instance:
                has_valid_links = self.instance.branch_accesses.filter(
                    is_active=True,
                    access_profile__status=Status.ACTIVE,
                    branch__company__user_accesses__user=self.instance,
                    branch__company__user_accesses__is_active=True,
                    branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
                ).exists()
            else:
                has_valid_links = False
            if not has_valid_links:
                raise serializers.ValidationError(
                    {'company_accesses': 'Usuarios com login precisam de ao menos uma filial com perfil.'}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        company_accesses = validated_data.pop('company_accesses')
        password = validated_data.pop('password', None)
        validated_data.setdefault('email', None)
        user = User.objects.create_user(password=password, **validated_data)
        replace_user_accesses(user=user, company_accesses=company_accesses)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        company_accesses = validated_data.pop('company_accesses', None)
        password = validated_data.pop('password', None)
        for attribute, value in validated_data.items():
            setattr(instance, attribute, value)
        if password:
            instance.set_password(password)
        if not instance.can_login:
            instance.set_unusable_password()
        instance.save()
        if company_accesses is not None:
            replace_user_accesses(user=instance, company_accesses=company_accesses)
        if not instance.can_login:
            UserCompanyAccess.objects.filter(user=instance).update(access_profile=None)
            UserBranchAccess.objects.filter(user=instance, is_active=True).update(
                is_active=False
            )
        return instance
