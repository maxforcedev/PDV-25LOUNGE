class PosOperator {
  const PosOperator({
    required this.id,
    required this.displayName,
    required this.initials,
    this.avatarUrl,
  });

  factory PosOperator.fromJson(Map<String, dynamic> json) => PosOperator(
        id: json['id'].toString(),
        displayName: json['display_name'] as String,
        initials: json['initials'] as String? ?? '',
        avatarUrl: json['avatar_url'] as String?,
      );

  final String id;
  final String displayName;
  final String initials;
  final String? avatarUrl;
}

class OperatorSession {
  const OperatorSession({required this.token, required this.operator});

  factory OperatorSession.fromJson(Map<String, dynamic> json) {
    final session = json['operator_session'] as Map<String, dynamic>;
    return OperatorSession(
      token: session['token'] as String,
      operator: PosOperator.fromJson(json['operator'] as Map<String, dynamic>),
    );
  }

  final String token;
  final PosOperator operator;
}
